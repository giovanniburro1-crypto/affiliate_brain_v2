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
    ["os", "device_type", "token2", "offer", "lander_id", "country", "traffic_source"]
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
        """Дневные метрики: roi, cr, impact. 1 row = 1 click, SUM по дням."""
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
            result.append({"roi": roi, "cr": cr, "impact": impact})
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
                        SELECT COALESCE({col}::text, '(empty)'),
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
        WEAKNESS: segment_cost / total_cost ≥ 10%,
        AND |segment_impact| / total_profit ≥ 10% (если total_profit > 0).
        При total_profit ≤ 0 — только условие по cost.
        Исключить очевидные: traffic_share >= 90%.
        Для сливающих кампаний (profit < 0): если нет сегментов по 10%, берём топ по spend (порог 5%).
        """
        if total_cost <= 0 or total_clicks <= 0:
            return []
        cost_share_min = 10
        if total_profit < 0 and total_cost >= 20:
            # При сливе и значительном spend — снижаем порог, чтобы показать сегменты
            cost_share_min = 5
        bad = []
        for s in segments:
            cost_share = (s["spend"] / total_cost) * 100
            if cost_share < cost_share_min:
                continue
            traffic_share = (s["clicks"] / total_clicks) * 100 if total_clicks else 0
            if traffic_share >= 90:
                continue
            if total_profit > 0:
                impact = s["revenue"] - s["spend"]
                impact_share = (abs(impact) / abs(total_profit)) * 100
                if impact_share < 10:
                    continue
            profit_pct = round((s["profit"] / total_profit) * 100, 0) if total_profit != 0 else 0
            bad.append({
                **s,
                "traffic_pct": round(traffic_share, 0),
                "profit_pct": int(profit_pct),
            })
        # Если всё ещё пусто при сливе — берём топ по |profit| среди минусовых
        if not bad and total_profit < 0 and total_cost >= 20:
            losing = [s for s in segments if s["profit"] < 0]
            losing.sort(key=lambda x: (-x["spend"], x["profit"]))
            for s in losing[:limit]:
                traffic_share = (s["clicks"] / total_clicks) * 100 if total_clicks else 0
                if traffic_share >= 90:
                    continue
                profit_pct = round((s["profit"] / total_profit) * 100, 0) if total_profit != 0 else 0
                bad.append({
                    **s,
                    "traffic_pct": round(traffic_share, 0),
                    "profit_pct": int(profit_pct),
                })
        bad.sort(key=lambda x: (x["profit"], -x["spend"]))
        return bad[:limit]

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
        Порядок: metrics → trend+volatility → add.monetization → proposition → POWER → WEAKNESS.
        Добавлена информация о голосах блоков.
        """
        lines = []
        c = campaign
        # 1. Metrics
        lines.append(
            f"ROI {c.get('roi', 0)}% • Profit ${c.get('profit', 0)} • Spend ${c.get('spend', 0)} • "
            f"Clicks {c.get('clicks', 0)} • Conv {c.get('conversions', 0)}"
        )
        # 2. Trend + Volatility
        trend_vol = trend_str
        if trend_vol:
            trend_vol += f"  Volatility {volatility:.1f}% • {days_with_data}/{total_days} дней"
        else:
            trend_vol = f"Volatility {volatility:.1f}% • {days_with_data}/{total_days} дней"
        lines.append(trend_vol)
        # 3. Add monetization
        if add_mon > 0:
            lines.append(f"Add.monetization ${add_mon} ({add_mon_pct}% of revenue)")
        # 4. Proposition
        if c.get("verdict") == "SCALE":
            lines.append("PROPOSITION: SCALE (low volatility, high ROI)")
        elif c.get("verdict") == "STOP":
            lines.append("PROPOSITION: STOP (negative ROI, no conversions)")
        elif c.get("verdict") == "OPTIMIZE":
            lines.append("PROPOSITION: OPTIMIZE (positive ROI, moderate volatility)")
        else:
            lines.append("PROPOSITION: HOLD (insufficient data)")
        # 5. POWER segments
        if power_segments:
            power_line = "POWER: "
            for i, s in enumerate(power_segments):
                if i > 0:
                    power_line += " • "
                power_line += f"{s['type']}={s['value']} ({s['traffic_pct']}% traffic, {s['profit_pct']}% profit)"
            lines.append(power_line)
        # 6. WEAKNESS segments
        if weakness_segments:
            weakness_line = "WEAKNESS: "
            for i, s in enumerate(weakness_segments):
                if i > 0:
                    weakness_line += " • "
                weakness_line += f"{s['type']}={s['value']} ({s['traffic_pct']}% traffic, {s['profit_pct']}% profit)"
            lines.append(weakness_line)
        # 7. Block votes (если есть)
        if block_votes:
            votes_line = "BLOCKS: "
            for vote in block_votes:
                block_name = vote.get('block_name', 'unknown')
                verdict = vote.get('verdict', 'UNKNOWN')
                confidence = vote.get('confidence', 0)
                # Display format: block_name+VERDICT(confidence%)
                votes_line += f"{block_name}+{verdict}({confidence:.1f}) "
            lines.append(votes_line.strip())
        return lines

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
        rows = self.db.execute(
            text("""
                SELECT campaign_id, campaign, traffic_source,
                       SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
                FROM traffic_stats
                WHERE date >= :d AND date <= :d_to
                GROUP BY campaign_id, campaign, traffic_source
                HAVING SUM(cost) >= :min_spend AND COUNT(*) >= :min_clicks
            """),
            {"d": date_from, "d_to": date_to, "min_spend": MIN_SPEND, "min_clicks": MIN_CLICKS},
        ).fetchall()
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
            try:
                analysis_result = self.brain.analyze_campaign(
                    campaign_id=cid,
                    roi=roi,
                    profit=profit,
                    spend=spend,
                    clicks=clicks,
                    conversions=conversions,
                    volatility=volatility,
                    daily_impact=daily_impact
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
            campaigns.append(
                {
                    "campaign_id": cid,
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
                SELECT campaign_id, campaign, traffic_source,
                       SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
                FROM traffic_stats
                WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
                GROUP BY campaign_id, campaign, traffic_source
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
        try:
            analysis_result = self.brain.analyze_campaign(
                campaign_id=campaign_id,
                roi=roi,
                profit=profit,
                spend=spend,
                clicks=clicks,
                conversions=conversions,
                volatility=volatility,
                daily_impact=daily_impact
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
