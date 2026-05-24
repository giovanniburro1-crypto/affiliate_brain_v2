"""
TOP-5 Bot Service V2 — отбор кампаний для масштабирования с использованием KnowledgeBaseV2.
Низкая волатильность = выше шанс на SCALE. Формат 4-6 строк (сила + слабость).
Использует KnowledgeBaseV2 для голосования блоков и обучения.
"""
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
import math
import json

from backend.brain.knowledge_base_v2_complete import KnowledgeBaseV2

# Пороги из спецификации
MIN_CLICKS = 100
MIN_DAYS_WITH_DATA = 3
MIN_SPEND = 15
CONFIDENCE_THRESHOLD = 95
SEGMENT_MIN_CLICKS = 1  # Было 5 — при разрозненном трафике Key Drivers пустые при $100+

# Разрешённые колонки для сегментации (защита от SQL injection)
_ALLOWED_SEGMENT_COLS = frozenset(
    ["os", "device_type", "token1", "token2", "token3", "token4", "token5", 
     "token6", "token7", "token8", "token9", "token10", "offer", "lander_id", 
     "country", "traffic_source"]
)
KILLER_SPEND_MULTIPLIER = 2.0
ZACEP_MIN_CONVERSIONS = 3
ZACEP_MIN_STABILITY_DAYS = 2


def _calc_volatility(
    daily_roi: List[float],
    daily_cr: List[float],
    daily_impact: List[float],
) -> float:
    """
    Волатильность по спецификации:
    Volatility_Score = (CV_ROI × 0.4) + (CV_CR × 0.3) + (RR_Impact × 0.3)
    RR_Impact использует AVG(impact) по требованию пользователя.
    """
    if len(daily_roi) < 3:
        return 0.0

    def cv(values: List[float]) -> float:
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        if mean == 0:
            return 0.0
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std = math.sqrt(variance) if variance > 0 else 0
        return (std / abs(mean)) * 100

    cv_roi = cv(daily_roi)
    cv_cr = cv(daily_cr) if daily_cr else 0.0

    # RR_Impact = (Max - Min) / AVG(impact). По требованию — среднее.
    if not daily_impact:
        rr_impact = 0.0
    else:
        avg_impact = sum(daily_impact) / len(daily_impact)
        if avg_impact == 0:
            rr_impact = 0.0
        else:
            rr_impact = (max(daily_impact) - min(daily_impact)) / abs(avg_impact)

    volatility = (cv_roi * 0.4) + (cv_cr * 0.3) + (rr_impact * 0.3)
    return round(volatility, 2)


def _calc_trend(daily_impact: List[float]) -> str:
    """IMPROVING / DECLINING / STABLE по последним дням (legacy)."""
    if len(daily_impact) < 4:
        return "UNKNOWN"
    mid = len(daily_impact) // 2
    first = sum(daily_impact[:mid]) / mid
    second = sum(daily_impact[mid:]) / (len(daily_impact) - mid)
    if second > first * 1.1:
        return "IMPROVING"
    if second < first * 0.9:
        return "DECLINING"
    return "STABLE"


def _calc_instability_index(daily_data: List[Dict[str, float]]) -> float:
    """
    Рассчитывает волатильность (0-100) по правилу "Только просадки":
    Мы не наказываем за рост ROI (даже сильные скачки вверх).
    Штраф (волатильный день) дается только если: Спенд > $15 И ROI < 10%.
    Это защищает кампании, куда лиды долетают пачками.
    """
    if len(daily_data) < 2:
        return 0.0
    
    volatile_days = 0
    total_days = len(daily_data)
    
    for day in daily_data:
        spend = day.get('cost', 0)
        roi = day.get('roi', 0)
        
        # Считаем день нестабильным только если потратили больше $10 и ROI меньше 20%
        if spend > 10 and roi < 20:
            volatile_days += 1

            
    return (volatile_days / total_days) * 100


def _instability_interpretation(instability: float) -> Dict[str, str]:
    """
    Возвращает интерпретацию значения волатильности.
    """
    if instability < 15:
        return {"level": "low", "color": "green", "label": "Стабильно", "description": "Кампания идет ровно. Идеальный момент для масштабирования бюджета."}
    elif instability <= 40:
        return {"level": "medium", "color": "yellow", "label": "Умеренно", "description": "Есть дневные колебания. Повышай бюджет осторожно, небольшими шагами."}
    else:
        return {"level": "high", "color": "red", "label": "Шторм", "description": "Высокий риск или мало лидов. Не рекомендуется менять бюджет прямо сейчас."}


def _calc_trend_last_n_days(daily_impact: List[float]) -> str:
    """
    ↑ last N days или ↓ last N days.
    N = длина последней подряд идущей серии положительного или отрицательного impact (min 2 дня).
    Если серия < 2 дней — возвращаем пустую строку или "—".
    """
    if not daily_impact or len(daily_impact) < 2:
        return ""
    count = 0
    first_sign = daily_impact[-1] >= 0
    for d in reversed(daily_impact):
        sign = d >= 0
        if sign == first_sign:
            count += 1
        else:
            break
    if count < 2:
        return ""
    if first_sign:
        return f"↑ last {count} days"
    return f"↓ last {count} days"


def _stability_factor(volatility: float) -> float:
    """Низкая волатильность = выше фактор. 1/(1+volatility/30)"""
    return 1.0 / (1.0 + volatility / 30.0)


def _opportunity_score(roi: float, clicks: int, volatility: float) -> float:
    """Opportunity_Score = ROI × Log10(Clicks+1) × Stability_Factor"""
    sf = _stability_factor(volatility)
    log_clicks = math.log10(clicks + 1) if clicks >= 0 else 0
    return roi * log_clicks * sf


class Top5ServiceV2:
    def __init__(self, db: Session, brain: Optional[KnowledgeBaseV2] = None):
        self.db = db
        self.brain = brain or KnowledgeBaseV2()
        self.block_votes = {}  # Кэш голосов блоков для текущего анализа

    def _period_or_range(
        self,
        period: int,
        date_from_str: Optional[str],
        date_to_str: Optional[str],
    ) -> Tuple[date, date]:
        today = date.today()
        if date_from_str and date_to_str:
            try:
                d_from = date.fromisoformat(date_from_str.strip()[:10])
                d_to = date.fromisoformat(date_to_str.strip()[:10])
                if d_from <= d_to:
                    return (d_from, d_to)
            except (ValueError, TypeError):
                pass
        return (today - timedelta(days=period), today)

    def _get_daily_metrics(
        self, campaign_id: str, date_from: date, date_to: date
    ) -> List[Dict[str, Any]]:
        """Дневные метрики: roi, cr, impact, conversions. 1 row = 1 click, SUM по дням."""
        rows = self.db.execute(
            text("""
                SELECT date,
                       SUM(cost) as cost,
                       SUM(revenue) as revenue,
                       SUM(conversions) as conv,
                       COUNT(*) as clicks
                FROM traffic_stats
                WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
                GROUP BY date
                ORDER BY date
            """),
            {"cid": campaign_id, "d": date_from, "d_to": date_to},
        ).fetchall()

        result = []
        for r in rows:
            cost = float(r[1] or 0)
            rev = float(r[2] or 0)
            conv = int(r[3] or 0)
            clk = int(r[4] or 0)
            impact = rev - cost
            roi = ((rev - cost) / cost * 100) if cost > 0 else 0.0
            cr = (conv / clk * 100) if clk > 0 else 0.0
            result.append({"roi": roi, "cr": cr, "impact": impact, "conversions": conv})
        return result

    def _get_campaign_segments(
        self,
        campaign_id: str,
        traffic_source: Optional[str],
        date_from: date,
        date_to: date,
        min_clicks: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Сегменты по колонкам из segment_config. min_clicks: если None — SEGMENT_MIN_CLICKS."""
        cols = self.brain.get_segment_columns(traffic_source)
        segments = []
        params = {"cid": campaign_id, "d": date_from, "d_to": date_to}
        mc = min_clicks if min_clicks is not None else SEGMENT_MIN_CLICKS

        for col in cols:
            if col not in _ALLOWED_SEGMENT_COLS:
                continue
            try:
                # Используем только whitelist колонок
                rows = self.db.execute(
                    text(f"""
                        SELECT COALESCE(CAST({col} AS TEXT), '(empty)'),
                               SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
                        FROM traffic_stats
                        WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
                        GROUP BY {col}
                        HAVING COUNT(*) >= :min_clicks
                        ORDER BY SUM(revenue) - SUM(cost) DESC
                    """),
                    {**params, "min_clicks": mc},
                ).fetchall()
            except Exception:
                continue
            for r in rows:
                spend = int(r[1] or 0)
                rev = int(r[2] or 0)
                conv = int(r[3] or 0)
                clk = int(r[4] or 0)
                profit = rev - spend
                roi = round((profit / spend * 100) if spend > 0 else 0)
                segments.append(
                    {
                        "type": col,
                        "value": r[0] or "(empty)",
                        "spend": spend,
                        "revenue": rev,
                        "conversions": conv,
                        "clicks": clk,
                        "profit": profit,
                        "roi": roi,
                    }
                )
        return segments

    def _find_power_segments(
        self,
        segments: List[Dict],
        total_profit: float,
        total_clicks: int,
        limit: int = 3,
    ) -> List[Dict]:
        """
        POWER: segment_profit / total_profit ≥ 10%.
        Исключить очевидные: segment_clicks / total_clicks >= 90%.
        Max 3. X% traffic volume, Y% profit traffic.
        """
        if total_profit <= 0 or total_clicks <= 0:
            return []
        good = []
        for s in segments:
            if s["profit"] <= 0:
                continue
            profit_share = (s["profit"] / total_profit) * 100
            if profit_share < 10:
                continue
            traffic_share = (s["clicks"] / total_clicks) * 100 if total_clicks else 0
            if traffic_share >= 90:
                continue
            good.append({**s, "traffic_pct": round(traffic_share, 0), "profit_pct": round(profit_share, 0)})
        good.sort(key=lambda x: (x["profit"], x["roi"]), reverse=True)
        return good[:limit]

    def _find_weakness_segments(
        self,
        segments: List[Dict],
        total_cost: float,
        total_profit: float,
        total_clicks: int,
        limit: int = 5,
    ) -> List[Dict]:
        """
        WEAKNESS: показывает ТОЛЬКО сегменты с отрицательным profit (то, что тянет кампанию вниз).
        Цель: пользователь видит, что конкретно сливает, и решает — оптимизировать или стопать.
        Без ограничения по traffic_share (если 88% трафика сливает — это и есть главная проблема).
        """
        if total_cost <= 0 or total_clicks <= 0:
            return []

        # Берём только сегменты, которые РЕАЛЬНО теряют деньги
        losing = []
        for s in segments:
            if s["profit"] >= 0:
                continue  # не показываем прибыльные — это не weakness
            traffic_share = (s["clicks"] / total_clicks) * 100 if total_clicks else 0
            loss_dollars = abs(s["profit"])
            # Доля убытка: сколько % от общего убытка приходится на этот сегмент
            # Если кампания в целом в минусе: loss_share = segment_loss / total_loss * 100
            total_loss = abs(total_profit) if total_profit < 0 else 1
            loss_share = round((loss_dollars / total_loss) * 100, 0) if total_loss > 0 else 0
            losing.append({
                **s,
                "traffic_pct": round(traffic_share, 0),
                "profit_pct": -int(loss_share),  # всегда отрицательный для WEAKNESS
                "loss_dollars": round(loss_dollars, 2),
            })

        # Сортируем: самые большие убытки первыми
        losing.sort(key=lambda x: x["profit"])
        return losing[:limit]

    def _check_zacepy(self, segments: List[Dict]) -> bool:
        """Есть ли зацепы: сегмент с min_conversions и profit > 0."""
        rules = self.brain.get_zacep_rules()
        min_conv = rules.get("min_conversions", ZACEP_MIN_CONVERSIONS)
        for s in segments:
            if s["conversions"] >= min_conv and s["profit"] > 0:
                return True
        return False

    def _find_profit_killers(
        self,
        segments: List[Dict],
        campaign_revenue: float,
        campaign_conversions: int,
        campaign_spend: float,
    ) -> List[Dict]:
        """
        Киллеры: сегмент с 0 конверсий и spend > 2× (revenue/conversions).
        Payout = revenue. cost_per_conv = revenue/conversions.
        Рекомендуем отключать только если есть зацепы.
        Если 0 конверсий по кампании и слив — киллеры: сегменты с 0 conv и spend >= $15 (или 10% от spend).
        """
        killers = []
        if campaign_conversions <= 0:
            # Кампания без конверсий и со сливом — показываем сегменты с 0 conv и значительным spend
            if campaign_spend < 20:
                return []
            threshold = max(15, campaign_spend * 0.1)
            for s in segments:
                if s["conversions"] == 0 and s["spend"] >= threshold:
                    killers.append({
                        "type": s["type"],
                        "value": s["value"],
                        "spend": s["spend"],
                        "threshold": round(threshold, 2),
                    })
            return killers[:5]  # топ 5 киллеров
        cost_per_conv = campaign_revenue / campaign_conversions
        threshold = cost_per_conv * KILLER_SPEND_MULTIPLIER
        for s in segments:
            if s["conversions"] == 0 and s["spend"] >= threshold:
                killers.append(
                    {
                        "type": s["type"],
                        "value": s["value"],
                        "spend": s["spend"],
                        "threshold": round(threshold, 2),
                    }
                )
        return killers

    def _build_summary_lines(
        self,
        campaign: Dict,
        power_segments: List[Dict],
        weakness_segments: List[Dict],
        add_mon: float,
        add_mon_pct: float,
        days_with_data: int,
        total_days: int,
        volatility: float,
        trend_str: str,
        block_votes: Optional[List[Dict]] = None,
    ) -> List[str]:
        """
        Компактный формат: 1-2 строки с ключевой информацией.
        1. Метрики + вердикт
        2. Ключевые сегменты (POWER/WEAKNESS)
        Блок BLOCKS не включается, так как отображается в таблице ниже.
        """
        lines = []
        c = campaign
        
        # 1. Первая строка: ключевые метрики и вердикт в компактном виде
        verdict_text = ""
        if c.get("verdict") == "SCALE":
            verdict_text = "• SCALE (low volatility, high ROI)"
        elif c.get("verdict") == "STOP":
            verdict_text = "• STOP (negative ROI)"
        elif c.get("verdict") == "OPTIMIZE":
            verdict_text = "• OPTIMIZE"
        else:
            verdict_text = "• HOLD"
            
        # Компактный формат метрик
        metrics_line = f"ROI {c.get('roi', 0)}% • ${c.get('profit', 0)} profit • ${c.get('spend', 0)} spend • {c.get('clicks', 0)} clicks • {c.get('conversions', 0)} conv"
        
        # Добавляем вердикт к метрикам
        first_line = f"{metrics_line} {verdict_text}"
        lines.append(first_line)
        
        # 2. Вторая строка: POWER и WEAKNESS сегменты (кратко)
        segments_line = ""
        
        # POWER сегменты (максимум 2 самых важных)
        if power_segments:
            top_power = power_segments[:2]
            power_parts = []
            for s in top_power:
                power_parts.append(f"{s['type']}={s['value']} ({s['profit_pct']}% profit)")
            segments_line += "POWER: " + " • ".join(power_parts)
            
        # WEAKNESS сегменты (максимум 2 самых проблемных)  
        if weakness_segments:
            top_weakness = weakness_segments[:2]
            if segments_line:
                segments_line += " • "
            weakness_parts = []
            for s in top_weakness:
                loss = s.get('loss_dollars', abs(s.get('profit', 0)))
                weakness_parts.append(f"{s['type']}={s['value']} (-${loss} loss)")
            segments_line += "WEAKNESS: " + " • ".join(weakness_parts)
            
        if segments_line:
            lines.append(segments_line)
            
        # 3. Дополнительная информация только если есть адд.монетизация
        if add_mon > 0:
            lines.append(f"Add.monetization ${add_mon} ({add_mon_pct}% of revenue)")
            
        # 4. Волатильность и тренд добавляем только если есть место (максимум 2 строки)
        # Но по требованию пользователя - только 1-2 строки, так что не добавляем
        
        # Блок BLOCKS не включаем - отображается в таблице ниже
        
        return lines
    
    def _generate_selection_reason(
        self,
        roi: float,
        profit: float,
        spend: float,
        clicks: int,
        conversions: int,
        volatility: float,
        verdict: str,
        opportunity_score: float,
        power_segments: List[Dict],
        weakness_segments: List[Dict],
        days_with_data: int,
    ) -> str:
        """
        Генерирует объяснение на русском языке, почему бот отобрал эту кампанию в топ-5.
        """
        reasons = []
        
        # 1. Основные метрики
        if roi > 30:
            reasons.append(f"высокий ROI ({roi}%)")
        elif roi > 15:
            reasons.append(f"хороший ROI ({roi}%)")
        elif roi > 0:
            reasons.append(f"положительный ROI ({roi}%)")
        elif roi <= -20:
            reasons.append(f"критически низкий ROI ({roi}%) - требуется остановка")
        else:
            reasons.append(f"ROI {roi}%")
            
        if profit > 0:
            reasons.append(f"прибыль ${profit}")
        else:
            reasons.append(f"убыток ${abs(profit)}")
            
        if clicks >= 1000:
            reasons.append(f"большой объём кликов ({clicks})")
        elif clicks >= 100:
            reasons.append(f"достаточный объём кликов ({clicks})")
            
        if conversions >= 3:
            reasons.append(f"конверсии ({conversions})")
            
        # 2. Волатильность и стабильность
        if volatility < 10:
            reasons.append(f"очень низкая волатильность ({volatility}%)")
        elif volatility < 20:
            reasons.append(f"низкая волатильность ({volatility}%)")
        elif volatility > 50:
            reasons.append(f"высокая волатильность ({volatility}%)")
            
        # 3. Вердикт
        verdict_explanation = {
            "SCALE": "рекомендуется масштабирование из-за высокой прибыльности и стабильности",
            "OPTIMIZE": "требуется оптимизация для улучшения показателей",
            "HOLD": "рекомендуется удержание текущих позиций",
            "STOP": "требуется остановка из-за негативных показателей"
        }
        if verdict in verdict_explanation:
            reasons.append(verdict_explanation[verdict])
            
        # 4. Сегменты
        if power_segments:
            top_power = power_segments[0]
            reasons.append(f"сильные сегменты ({top_power['type']}={top_power['value']} даёт {top_power['profit_pct']}% прибыли)")
            
        if weakness_segments:
            top_weakness = weakness_segments[0]
            loss = top_weakness.get('loss_dollars', abs(top_weakness.get('profit', 0)))
            reasons.append(f"слабые сегменты ({top_weakness['type']}={top_weakness['value']} теряет ${loss})")
            
        # 5. Opportunity Score
        if opportunity_score > 100:
            reasons.append(f"высокий потенциал для масштабирования (скор: {opportunity_score:.1f})")
        elif opportunity_score > 50:
            reasons.append(f"хороший потенциал для масштабирования (скор: {opportunity_score:.1f})")
            
        # 6. Данные за дни
        if days_with_data >= 7:
            reasons.append(f"стабильные данные за {days_with_data} дней")
        elif days_with_data >= 3:
            reasons.append(f"данные за {days_with_data} дня")
            
        # Формируем итоговое объяснение
        if reasons:
            explanation = "Бот отобрал кампанию в топ-5 потому что: " + ", ".join(reasons) + "."
        else:
            explanation = "Кампания отобрана на основе комплексного анализа метрик."
            
        return explanation

    def get_top5(
        self,
        period: int = 7,
        date_from_str: Optional[str] = None,
        date_to_str: Optional[str] = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Топ-5 кампаний для масштабирования."""
        date_from, date_to = self._period_or_range(period, date_from_str, date_to_str)
        total_days = (date_to - date_from).days + 1
        
        # Получаем campaign_id, которые находятся в recheck_queue и срок еще не истек
        excluded_campaigns = []
        try:
            excluded_rows = self.db.execute(
                text("""
                    SELECT campaign_id 
                    FROM recheck_queue 
                    WHERE recheck_after_days = 0 
                       OR (datetime(applied_at, '+' || recheck_after_days || ' days') > date('now'))
                """)
            ).fetchall()
            excluded_campaigns = [row[0] for row in excluded_rows]
        except Exception:
            # Таблицы может не существовать, игнорируем
            pass

        # Также исключаем кампании, у которых в имени есть "STOP - "
        try:
            stopped_rows = self.db.execute(
                text("""SELECT DISTINCT campaign_id
                    FROM traffic_stats t1
                    WHERE date = (SELECT MAX(date) FROM traffic_stats t2 WHERE t2.campaign_id = t1.campaign_id)
                      AND (campaign LIKE '%STOP -%' OR campaign LIKE '%stop -%')""")
            ).fetchall()
            excluded_campaigns.extend([row[0] for row in stopped_rows])
            excluded_campaigns = list(set(excluded_campaigns))
        except Exception:
            pass

        
        # Базовый SQL запрос
        sql = """
            SELECT campaign_id, MAX(COALESCE(date, '') || '|||' || campaign), MAX(traffic_source),
                   SUM(cost), SUM(revenue), SUM(conversions), COUNT(*), MAX(token1)
            FROM traffic_stats
            WHERE date >= :d AND date <= :d_to
        """
        
        # Добавляем условие исключения, если есть исключаемые кампании
        params = {"d": date_from, "d_to": date_to, "min_spend": MIN_SPEND, "min_clicks": MIN_CLICKS}
        if excluded_campaigns:
            sql += f" AND campaign_id NOT IN ({','.join([':ex' + str(i) for i in range(len(excluded_campaigns))])})"
            for i, ec in enumerate(excluded_campaigns):
                params[f"ex{i}"] = ec
        
        sql += """
            GROUP BY campaign_id
            HAVING SUM(cost) >= :min_spend AND COUNT(*) >= :min_clicks
        """

        
        rows = self.db.execute(text(sql), params).fetchall()
        campaigns = []
        for row in rows:
            cid = row[0]
            spend = int(round(float(row[3] or 0)))
            base_revenue = int(round(float(row[4] or 0)))
            conversions = int(row[5] or 0)
            clicks = int(row[6] or 0)
            add_mon = self.db.execute(
                text("""
                    SELECT COALESCE(SUM(revenue),0) FROM additional_monetization
                    WHERE campaign_id = :c AND date >= :d AND date <= :d_to
                """),
                {"c": cid, "d": date_from, "d_to": date_to},
            ).scalar() or 0
            add_mon = int(round(float(add_mon)))
            revenue = base_revenue + add_mon
            profit = revenue - spend
            roi = round((profit / spend * 100) if spend > 0 else 0)
            add_mon_pct = round((add_mon / revenue * 100), 1) if revenue > 0 else 0.0
            daily = self._get_daily_metrics(cid, date_from, date_to)
            days_with_data = len(daily)
            if days_with_data < 1:
                days_with_data = 1
            daily_roi = [d["roi"] for d in daily]
            daily_cr = [d["cr"] for d in daily]
            daily_impact = [d["impact"] for d in daily]
            volatility = _calc_instability_index(daily)
            trend = _calc_trend(daily_impact)
            opp_score = _opportunity_score(roi, clicks, volatility)
            stability_factor = _stability_factor(volatility)
            killer_rules = self.brain.get_killer_rules()
            verdict = "HOLD"
            if roi < killer_rules.get("roi_threshold", -20):
                verdict = "STOP"
            elif profit < 0 and conversions == 0 and spend > 100:
                verdict = "STOP"
            elif roi >= 30 and volatility < 15 and conversions >= 3:
                verdict = "SCALE"
            elif roi >= 15 and volatility < 10 and conversions >= 3:
                verdict = "SCALE"
            elif 0 < roi < 15:
                verdict = "OPTIMIZE"
            neg_streak = 0
            for d in reversed(daily):
                if d["impact"] < 0:
                    neg_streak += 1
                else:
                    break
            if neg_streak >= 3:
                verdict = "STOP"
            confidence = min(100, max(10, (days_with_data / 14) * 50 + (clicks / 1000) * 30 - (volatility / 100) * 20 + stability_factor * 15))
            confidence = round(confidence, 1)
            # Получаем голоса блоков
            block_votes = []
            
            payout = (revenue / conversions) if conversions > 0 else 0.0
            epc = (revenue / clicks) if clicks > 0 else 0.0
            cpc = (spend / clicks) if clicks > 0 else 0.0
            
            try:
                analysis_result = self.brain.analyze_campaign(
                    campaign_id=cid,
                    roi=roi,
                    profit=profit,
                    spend=spend,
                    clicks=clicks,
                    conversions=conversions,
                    volatility=volatility,
                    daily_impact=daily_impact,
                    payout=payout,
                    epc=epc,
                    cpc=cpc
                )
                if analysis_result and "block_votes" in analysis_result:
                    block_votes = analysis_result["block_votes"]
            except Exception as e:
                pass
            segments = self._get_campaign_segments(cid, row[2], date_from, date_to)
            power_segments = self._find_power_segments(segments, profit, clicks, limit=3)
            weakness_segments = self._find_weakness_segments(segments, spend, profit, clicks, limit=5)
            # Не показывать один и тот же сегмент и как силу, и как слабость
            power_keys = {(s["type"], str(s["value"])) for s in power_segments}
            weakness_segments = [w for w in weakness_segments if (w["type"], str(w["value"])) not in power_keys]
            has_zacepy = self._check_zacepy(segments)
            killers = self._find_profit_killers(segments, revenue, conversions, spend)
            if killers and not has_zacepy and conversions > 0:
                killers = []
            trend_str = _calc_trend_last_n_days(daily_impact)
            summary_lines = self._build_summary_lines(
                {"roi": roi, "profit": profit, "spend": spend, "clicks": clicks, "conversions": conversions, "verdict": verdict},
                power_segments, weakness_segments, add_mon, add_mon_pct, days_with_data, total_days, volatility, trend_str, block_votes,
            )
            explanation = self._generate_selection_reason(
                roi=roi,
                profit=profit,
                spend=spend,
                clicks=clicks,
                conversions=conversions,
                volatility=volatility,
                verdict=verdict,
                opportunity_score=round(opp_score, 2),
                power_segments=power_segments,
                weakness_segments=weakness_segments,
                days_with_data=days_with_data,
            )
            campaigns.append(
                {
                    "campaign_id": cid,
                    "campaign": row[1].split('|||', 1)[1] if row[1] and '|||' in row[1] else row[1],
                    "source": row[2],
                    "token1": row[7],
                    "spend": spend,
                    "revenue": revenue,
                    "profit": profit,
                    "roi": roi,
                    "conversions": conversions,
                    "clicks": clicks,
                    "add_mon": add_mon,
                    "add_mon_pct": add_mon_pct,
                    "volatility": volatility,
                    "days_with_data": days_with_data,
                    "total_days": total_days,
                    "opportunity_score": round(opp_score, 2),
                    "verdict": verdict,
                    "confidence": confidence,
                    "bot_score": round(opp_score / 5, 1),
                    "summary_lines": summary_lines,
                    "reasoning": "; ".join(summary_lines),
                    "explanation": explanation,
                    "strengths": power_segments,
                    "weaknesses": weakness_segments,
                    "profit_killers": killers,
                    "trend": trend,
                    "block_votes": block_votes,
                }
            )
        campaigns.sort(key=lambda x: x["opportunity_score"], reverse=True)
        top = campaigns[:limit]
        return self._format_result(campaigns, top, limit)

    def get_campaign_analysis(
        self,
        campaign_id: str,
        period: int = 7,
        date_from_str: Optional[str] = None,
        date_to_str: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Анализ одной кампании по ID."""
        date_from, date_to = self._period_or_range(period, date_from_str, date_to_str)
        total_days = (date_to - date_from).days + 1
        row = self.db.execute(
            text("""
                SELECT campaign_id, MAX(COALESCE(date, '') || '|||' || campaign), MAX(traffic_source),
                       SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
                FROM traffic_stats
                WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
                GROUP BY campaign_id

            """),
            {"cid": campaign_id, "d": date_from, "d_to": date_to},
        ).fetchone()
        if not row:
            return None
        spend = int(round(float(row[3] or 0)))
        base_revenue = int(round(float(row[4] or 0)))
        conversions = int(row[5] or 0)
        clicks = int(row[6] or 0)
        add_mon = self.db.execute(
            text("""
                SELECT COALESCE(SUM(revenue),0) FROM additional_monetization
                WHERE campaign_id = :c AND date >= :d AND date <= :d_to
            """),
            {"c": campaign_id, "d": date_from, "d_to": date_to},
        ).scalar() or 0
        add_mon = int(round(float(add_mon)))
        revenue = base_revenue + add_mon
        profit = revenue - spend
        roi = round((profit / spend * 100) if spend > 0 else 0)
        add_mon_pct = round((add_mon / revenue * 100), 1) if revenue > 0 else 0.0
        daily = self._get_daily_metrics(campaign_id, date_from, date_to)
        days_with_data = len(daily)
        if days_with_data < 1:
            days_with_data = 1
        daily_roi = [d["roi"] for d in daily]
        daily_cr = [d["cr"] for d in daily]
        daily_impact = [d["impact"] for d in daily]
        volatility = _calc_volatility(daily_roi, daily_cr, daily_impact)
        trend = _calc_trend(daily_impact)
        opp_score = _opportunity_score(roi, clicks, volatility)
        stability_factor = _stability_factor(volatility)
        killer_rules = self.brain.get_killer_rules()
        verdict = "HOLD"
        if roi < killer_rules.get("roi_threshold", -20):
            verdict = "STOP"
        elif profit < 0 and conversions == 0 and spend > 100:
            verdict = "STOP"
        elif roi >= 30 and volatility < 15 and conversions >= 3:
            verdict = "SCALE"
        elif roi >= 15 and volatility < 10 and conversions >= 3:
            verdict = "SCALE"
        elif 0 < roi < 15:
            verdict = "OPTIMIZE"
        neg_streak = 0
        for d in reversed(daily):
            if d["impact"] < 0:
                neg_streak += 1
            else:
                break
        if neg_streak >= 3:
            verdict = "STOP"
        confidence = min(100, max(10, (days_with_data / 14) * 50 + (clicks / 1000) * 30 - (volatility / 100) * 20 + stability_factor * 15))
        confidence = round(confidence, 1)
        # Получаем голоса блоков
        block_votes = []
        
        payout = (revenue / conversions) if conversions > 0 else 0.0
        epc = (revenue / clicks) if clicks > 0 else 0.0
        cpc = (spend / clicks) if clicks > 0 else 0.0
        
        try:
            analysis_result = self.brain.analyze_campaign(
                campaign_id=campaign_id,
                roi=roi,
                profit=profit,
                spend=spend,
                clicks=clicks,
                conversions=conversions,
                volatility=volatility,
                daily_impact=daily_impact,
                payout=payout,
                epc=epc,
                cpc=cpc
            )
            if analysis_result and "block_votes" in analysis_result:
                block_votes = analysis_result["block_votes"]
        except Exception as e:
            pass
        segments = self._get_campaign_segments(campaign_id, row[2], date_from, date_to)
        power_segments = self._find_power_segments(segments, profit, clicks, limit=3)
        weakness_segments = self._find_weakness_segments(segments, spend, profit, clicks, limit=5)
        # Не показывать один и тот же сегмент и как силу, и как слабость
        power_keys = {(s["type"], str(s["value"])) for s in power_segments}
        weakness_segments = [w for w in weakness_segments if (w["type"], str(w["value"])) not in power_keys]
        has_zacepy = self._check_zacepy(segments)
        killers = self._find_profit_killers(segments, revenue, conversions, spend)
        if killers and not has_zacepy and conversions > 0:
            killers = []
        trend_str = _calc_trend_last_n_days(daily_impact)
        summary_lines = self._build_summary_lines(
            {"roi": roi, "profit": profit, "spend": spend, "clicks": clicks, "conversions": conversions, "verdict": verdict},
            power_segments, weakness_segments, add_mon, add_mon_pct, days_with_data, total_days, volatility, trend_str, block_votes,
        )
        return {
            "campaign_id": campaign_id,
            "campaign": row[1],
            "source": row[2],
            "spend": spend,
            "revenue": revenue,
            "profit": profit,
            "roi": roi,
            "conversions": conversions,
            "clicks": clicks,
            "add_mon": add_mon,
            "add_mon_pct": add_mon_pct,
            "volatility": volatility,
            "days_with_data": days_with_data,
            "total_days": total_days,
            "opportunity_score": round(opp_score, 2),
            "verdict": verdict,
            "confidence": confidence,
            "bot_score": round(opp_score / 5, 1),
            "summary_lines": summary_lines,
            "reasoning": "; ".join(summary_lines),
            "strengths": power_segments,
            "weaknesses": weakness_segments,
            "profit_killers": killers,
            "trend": trend,
            "block_votes": block_votes,
        }

    def _format_result(
        self,
        campaigns: List[Dict],
        top: List[Dict],
        limit: int,
    ) -> Dict[str, Any]:
        summary = {
            "total_profit": sum(c["profit"] for c in campaigns),
            "scale_count": len([c for c in campaigns if c["verdict"] == "SCALE"]),
            "stop_count": len([c for c in campaigns if c["verdict"] == "STOP"]),
        }
        return {
            "campaigns": top,
            "all_campaigns": campaigns,
            "summary": summary,
        }

    def get_stop_optimize(
        self,
        period: int = 30,
        date_from_str: Optional[str] = None,
        date_to_str: Optional[str] = None,
        max_roi: Optional[float] = None,
        min_cost: Optional[float] = None,
        min_neg_streak: Optional[int] = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """
        Топ-N самых убыточных кампаний для страницы STOP & OPTIMIZATION.
        Сортировка: рецидивисты (STOP + живой трафик) → убыток по убыванию.
        Фильтры применяются только если не None.
        """
        date_from, date_to = self._period_or_range(period, date_from_str, date_to_str)
        total_days = (date_to - date_from).days + 1

        # --- Исключаем кампании в recheck_queue (OPTIMIZE/HOLD со сроком) ---
        excluded_campaigns: List[str] = []
        try:
            excluded_rows = self.db.execute(
                text("""
                    SELECT campaign_id
                    FROM recheck_queue
                    WHERE recheck_after_days = 0
                       OR (datetime(applied_at, '+' || recheck_after_days || ' days') > date('now'))
                """)
            ).fetchall()
            excluded_campaigns = [row[0] for row in excluded_rows]
        except Exception:
            pass

        # Также исключаем кампании, у которых в имени есть "STOP - "
        try:
            stopped_rows = self.db.execute(
                text("""SELECT DISTINCT campaign_id
                    FROM traffic_stats t1
                    WHERE date = (SELECT MAX(date) FROM traffic_stats t2 WHERE t2.campaign_id = t1.campaign_id)
                      AND (campaign LIKE '%STOP -%' OR campaign LIKE '%stop -%')""")
            ).fetchall()
            excluded_campaigns.extend([row[0] for row in stopped_rows])
            excluded_campaigns = list(set(excluded_campaigns))
        except Exception:
            pass

        # --- Запоминаем кампании, которые были STOP'd ранее (рецидивисты) ---
        stopped_campaign_ids: set = set()
        try:
            stopped_rows = self.db.execute(
                text("""
                    SELECT DISTINCT campaign_id FROM ai_memory
                    WHERE user_choice = 'STOP' OR bot_verdict = 'STOP'
                """)
            ).fetchall()
            stopped_campaign_ids = {row[0] for row in stopped_rows}
        except Exception:
            pass

        # --- Базовый SQL: все кампании за период ---
        sql = """
            SELECT campaign_id, MAX(COALESCE(date, '') || '|||' || campaign), MAX(traffic_source),
                   SUM(cost), SUM(revenue), SUM(conversions), COUNT(*), MAX(token1)
            FROM traffic_stats
            WHERE date >= :d AND date <= :d_to
        """
        params: Dict[str, Any] = {
            "d": date_from, "d_to": date_to,
            "min_spend": min_cost if min_cost is not None else MIN_SPEND,
            "min_clicks": MIN_CLICKS,
        }

        # Исключаем кампании из recheck_queue (OPTIMIZE/HOLD)
        if excluded_campaigns:
            sql += f" AND campaign_id NOT IN ({','.join([':ex' + str(i) for i in range(len(excluded_campaigns))])})"
            for i, ec in enumerate(excluded_campaigns):
                params[f"ex{i}"] = ec

        sql += """
            GROUP BY campaign_id
            HAVING SUM(cost) >= :min_spend AND COUNT(*) >= :min_clicks
        """

        rows = self.db.execute(text(sql), params).fetchall()

        campaigns: List[Dict] = []
        for row in rows:
            cid = row[0]
            spend = int(round(float(row[3] or 0)))
            base_revenue = int(round(float(row[4] or 0)))
            conversions = int(row[5] or 0)
            clicks = int(row[6] or 0)

            # Доп. монетизация
            add_mon = self.db.execute(
                text("""
                    SELECT COALESCE(SUM(revenue),0) FROM additional_monetization
                    WHERE campaign_id = :c AND date >= :d AND date <= :d_to
                """),
                {"c": cid, "d": date_from, "d_to": date_to},
            ).scalar() or 0
            add_mon = int(round(float(add_mon)))
            revenue = base_revenue + add_mon
            profit = revenue - spend
            roi = round((profit / spend * 100) if spend > 0 else 0)
            add_mon_pct = round((add_mon / revenue * 100), 1) if revenue > 0 else 0.0

            # Дневные метрики
            daily = self._get_daily_metrics(cid, date_from, date_to)
            days_with_data = max(len(daily), 1)
            daily_roi = [d["roi"] for d in daily]
            daily_cr = [d["cr"] for d in daily]
            daily_impact = [d["impact"] for d in daily]
            volatility = _calc_instability_index(daily)
            trend = _calc_trend(daily_impact)
            opp_score = _opportunity_score(roi, clicks, volatility)
            stability_factor = _stability_factor(volatility)

            # Считаем negative streak
            neg_streak = 0
            for d in reversed(daily):
                if d["impact"] < 0:
                    neg_streak += 1
                else:
                    break

            # --- Пользовательские фильтры (только если не None) ---
            if max_roi is not None and roi > max_roi:
                continue
            if min_cost is not None and spend < min_cost:
                continue
            if min_neg_streak is not None and neg_streak < min_neg_streak:
                continue

            # Вердикт
            killer_rules = self.brain.get_killer_rules()
            verdict = "HOLD"
            if roi < killer_rules.get("roi_threshold", -20):
                verdict = "STOP"
            elif profit < 0 and conversions == 0 and spend > 100:
                verdict = "STOP"
            elif roi >= 30 and volatility < 15 and conversions >= 3:
                verdict = "SCALE"
            elif roi >= 15 and volatility < 10 and conversions >= 3:
                verdict = "SCALE"
            elif 0 < roi < 15:
                verdict = "OPTIMIZE"
            if neg_streak >= 3:
                verdict = "STOP"

            confidence = min(100, max(10, (days_with_data / 14) * 50 + (clicks / 1000) * 30 - (volatility / 100) * 20 + stability_factor * 15))
            confidence = round(confidence, 1)

            # Голоса блоков (обучение бота)
            block_votes: List[Dict] = []
            payout = (revenue / conversions) if conversions > 0 else 0.0
            epc = (revenue / clicks) if clicks > 0 else 0.0
            cpc = (spend / clicks) if clicks > 0 else 0.0
            try:
                analysis_result = self.brain.analyze_campaign(
                    campaign_id=cid, roi=roi, profit=profit, spend=spend,
                    clicks=clicks, conversions=conversions, volatility=volatility,
                    daily_impact=daily_impact, payout=payout, epc=epc, cpc=cpc,
                )
                if analysis_result and "block_votes" in analysis_result:
                    block_votes = analysis_result["block_votes"]
            except Exception:
                pass

            # Сегменты
            segments = self._get_campaign_segments(cid, row[2], date_from, date_to)
            power_segments = self._find_power_segments(segments, profit, clicks, limit=3)
            weakness_segments = self._find_weakness_segments(segments, spend, profit, clicks, limit=5)
            power_keys = {(s["type"], str(s["value"])) for s in power_segments}
            weakness_segments = [w for w in weakness_segments if (w["type"], str(w["value"])) not in power_keys]
            has_zacepy = self._check_zacepy(segments)
            killers = self._find_profit_killers(segments, revenue, conversions, spend)
            if killers and not has_zacepy and conversions > 0:
                killers = []
            trend_str = _calc_trend_last_n_days(daily_impact)

            summary_lines = self._build_summary_lines(
                {"roi": roi, "profit": profit, "spend": spend, "clicks": clicks, "conversions": conversions, "verdict": verdict},
                power_segments, weakness_segments, add_mon, add_mon_pct, days_with_data, total_days, volatility, trend_str, block_votes,
            )
            explanation = self._generate_selection_reason(
                roi=roi, profit=profit, spend=spend, clicks=clicks,
                conversions=conversions, volatility=volatility, verdict=verdict,
                opportunity_score=round(opp_score, 2),
                power_segments=power_segments, weakness_segments=weakness_segments,
                days_with_data=days_with_data,
            )

            # Флаг рецидивиста: был STOP, но трафик продолжается
            is_repeat_offender = cid in stopped_campaign_ids and spend > 0

            campaigns.append({
                "campaign_id": cid,
                "campaign": row[1].split('|||', 1)[1] if row[1] and '|||' in row[1] else row[1],
                "source": row[2],
                "token1": row[7],
                "spend": spend,
                "revenue": revenue,
                "profit": profit,
                "roi": roi,
                "conversions": conversions,
                "clicks": clicks,
                "add_mon": add_mon,
                "add_mon_pct": add_mon_pct,
                "volatility": volatility,
                "neg_streak": neg_streak,
                "days_with_data": days_with_data,
                "total_days": total_days,
                "opportunity_score": round(opp_score, 2),
                "verdict": verdict,
                "confidence": confidence,
                "bot_score": round(opp_score / 5, 1),
                "summary_lines": summary_lines,
                "reasoning": "; ".join(summary_lines),
                "explanation": explanation,
                "strengths": power_segments,
                "weaknesses": weakness_segments,
                "profit_killers": killers,
                "trend": trend,
                "block_votes": block_votes,
                "is_repeat_offender": is_repeat_offender,
            })

        # Сортировка: рецидивисты → потом по убытку (profit ASC)
        campaigns.sort(key=lambda x: (0 if x["is_repeat_offender"] else 1, x["profit"]))

        top = campaigns[:limit]
        total_loss = sum(c["profit"] for c in campaigns if c["profit"] < 0)
        stop_count = len([c for c in campaigns if c["verdict"] == "STOP"])
        optimize_count = len([c for c in campaigns if c["verdict"] == "OPTIMIZE"])

        return {
            "campaigns": top,
            "all_campaigns": campaigns,
            "total_count": len(campaigns),
            "summary": {
                "total_loss": total_loss,
                "stop_count": stop_count,
                "optimize_count": optimize_count,
            },
        }
