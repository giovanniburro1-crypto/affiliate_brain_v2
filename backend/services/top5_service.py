"""
TOP-5 Bot Service — отбор кампаний для масштабирования.
Низкая волатильность = выше шанс на SCALE. Формат 4-6 строк (сила + слабость).
Использует KnowledgeBase для правил, но логика отбора — отдельный блок.
"""
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
import math

from backend.brain import KnowledgeBase

# Пороги из спецификации
MIN_CLICKS = 100
MIN_DAYS_WITH_DATA = 3
MIN_SPEND = 15
CONFIDENCE_THRESHOLD = 95
SEGMENT_MIN_CLICKS = 15

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
    """IMPROVING / DECLINING / STABLE по последним дням."""
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


def _stability_factor(volatility: float) -> float:
    """Низкая волатильность = выше фактор. 1/(1+volatility/30)"""
    return 1.0 / (1.0 + volatility / 30.0)


def _opportunity_score(roi: float, clicks: int, volatility: float) -> float:
    """Opportunity_Score = ROI × Log10(Clicks+1) × Stability_Factor"""
    sf = _stability_factor(volatility)
    log_clicks = math.log10(clicks + 1) if clicks >= 0 else 0
    return roi * log_clicks * sf


class Top5Service:
    def __init__(self, db: Session, brain: Optional[KnowledgeBase] = None):
        self.db = db
        self.brain = brain or KnowledgeBase()

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
    ) -> List[Dict[str, Any]]:
        """Сегменты по колонкам из segment_config. Минимум 15-20 кликов на сегмент."""
        cols = self.brain.get_segment_columns(traffic_source)
        segments = []
        params = {"cid": campaign_id, "d": date_from, "d_to": date_to}

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
                    {**params, "min_clicks": SEGMENT_MIN_CLICKS},
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

    def _find_strengths(
        self, segments: List[Dict], limit: int = 2
    ) -> List[Dict]:
        """2 лучших сегмента по Impact и ROI (комбинация)."""
        good = [s for s in segments if s["profit"] > 0 and s["conversions"] >= 1]
        good.sort(key=lambda x: (x["profit"], x["roi"]), reverse=True)
        return good[:limit]

    def _find_weaknesses(
        self, segments: List[Dict], limit: int = 2
    ) -> List[Dict]:
        """2 худших сегмента (отрицательный impact или 0 conv при значимом spend)."""
        bad = [s for s in segments if s["profit"] < 0 or (s["conversions"] == 0 and s["spend"] > 0)]
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
        """
        if campaign_conversions <= 0:
            return []
        cost_per_conv = campaign_revenue / campaign_conversions
        threshold = cost_per_conv * KILLER_SPEND_MULTIPLIER
        killers = []
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
        strengths: List[Dict],
        weaknesses: List[Dict],
        killers: List[Dict],
        add_mon_pct: float,
        days_with_data: int,
        total_days: int,
        volatility: float,
    ) -> List[str]:
        """
        Формат 4-6 строк:
        1: ROI • Profit • Spend • Clicks • Conv
        2-3: [СИЛА] ...
        4-5: [СЛАБОСТЬ] ...
        6: [ВЫВОД] + доп. монетизация + волатильность
        """
        lines = []
        c = campaign
        lines.append(
            f"ROI {c.get('roi', 0)}% • Profit ${c.get('profit', 0)} • Spend ${c.get('spend', 0)} • "
            f"Clicks {c.get('clicks', 0)} • Conv {c.get('conversions', 0)}"
        )

        for s in strengths[:2]:
            cr = round((s["conversions"] / s["clicks"] * 100), 1) if s.get("clicks") else 0
            lines.append(
                f"[СИЛА] {s['type']} {s['value']}: CR {cr}% • Rev ${s['revenue']} • Profit ${s['profit']}"
            )
        if not strengths:
            lines.append("[СИЛА] Нет явных доноров профита")

        for w in weaknesses[:2]:
            lines.append(
                f"[СЛАБОСТЬ] {w['type']} {w['value']}: Rev ${w['revenue']} Cost ${w['spend']} Conv {w['conversions']}"
            )

        # Киллеры + вывод
        verdict = c.get("verdict", "HOLD")
        out = f"[ВЫВОД] {verdict}"
        if add_mon_pct > 0:
            out += f" • Доп. монетизация: {add_mon_pct:.0f}% профита"
        out += f" • Волатильность {volatility:.1f}% • {days_with_data}/{total_days} дней"
        if killers:
            out += f" • Stop: {', '.join(k['value'] for k in killers[:3])}"
        lines.append(out)
        return lines

    def get_top5(
        self,
        period: int = 30,
        date_from_str: Optional[str] = None,
        date_to_str: Optional[str] = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """
        Основной метод. Возвращает TOP-5 кампаний с полным форматом 4-6 строк.
        """
        date_from, date_to = self._period_or_range(period, date_from_str, date_to_str)
        total_days = (date_to - date_from).days + 1

        # Сырые кампании: spend > MIN_SPEND, exclude monetisation sources
        filter_monet = (
            "AND traffic_source != 'AddMonetisation' "
            "AND LOWER(traffic_source) NOT LIKE '%monetisation%'"
        )
        rows = self.db.execute(
            text(f"""
                SELECT campaign_id, campaign, traffic_source,
                       SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
                FROM traffic_stats
                WHERE date >= :d AND date <= :d_to AND campaign_id IS NOT NULL
                {filter_monet}
                GROUP BY campaign_id, campaign, traffic_source
                HAVING SUM(cost) >= :min_spend AND COUNT(*) >= :min_clicks
                ORDER BY SUM(revenue) - SUM(cost) DESC
                LIMIT 50
            """),
            {
                "d": date_from,
                "d_to": date_to,
                "min_spend": MIN_SPEND,
                "min_clicks": MIN_CLICKS,
            },
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
            add_mon_pct = round((add_mon / profit * 100), 1) if profit > 0 and add_mon > 0 else 0.0

            # Дневные метрики для волатильности
            daily = self._get_daily_metrics(cid, date_from, date_to)
            days_with_data = len(daily)
            if days_with_data < MIN_DAYS_WITH_DATA:
                continue

            daily_roi = [d["roi"] for d in daily]
            daily_cr = [d["cr"] for d in daily]
            daily_impact = [d["impact"] for d in daily]
            volatility = _calc_volatility(daily_roi, daily_cr, daily_impact)
            trend = _calc_trend(daily_impact)

            # Opportunity Score (низкая волатильность = лучше)
            opp_score = _opportunity_score(roi, clicks, volatility)
            stability_factor = _stability_factor(volatility)

            # Вердикт (упрощённо; полная логика может использовать Brain)
            verdict = "HOLD"
            killer_rules = self.brain.get_killer_rules()
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

            # Confidence
            confidence = min(
                100,
                max(
                    10,
                    (days_with_data / 14) * 50
                    + (clicks / 1000) * 30
                    - (volatility / 100) * 20
                    + (stability_factor * 15),
                ),
            )
            confidence = round(confidence, 1)

            # Сегменты
            segments = self._get_campaign_segments(
                cid, row[2], date_from, date_to
            )
            strengths = self._find_strengths(segments)
            weaknesses = self._find_weaknesses(segments)
            has_zacepy = self._check_zacepy(segments)
            killers = self._find_profit_killers(
                segments, revenue, conversions, spend
            )
            if killers and not has_zacepy:
                killers = []  # Не рекомендуем резать, если нет зацепов

            summary_lines = self._build_summary_lines(
                {
                    "roi": roi,
                    "profit": profit,
                    "spend": spend,
                    "clicks": clicks,
                    "conversions": conversions,
                    "verdict": verdict,
                },
                strengths,
                weaknesses,
                killers,
                add_mon_pct,
                days_with_data,
                total_days,
                volatility,
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
                    "strengths": strengths,
                    "weaknesses": weaknesses,
                    "profit_killers": killers,
                    "trend": trend,
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
        add_mon_pct = round((add_mon / profit * 100), 1) if profit > 0 and add_mon > 0 else 0.0
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
        segments = self._get_campaign_segments(campaign_id, row[2], date_from, date_to)
        strengths = self._find_strengths(segments)
        weaknesses = self._find_weaknesses(segments)
        has_zacepy = self._check_zacepy(segments)
        killers = self._find_profit_killers(segments, revenue, conversions, spend)
        if killers and not has_zacepy:
            killers = []
        summary_lines = self._build_summary_lines(
            {"roi": roi, "profit": profit, "spend": spend, "clicks": clicks, "conversions": conversions, "verdict": verdict},
            strengths, weaknesses, killers, add_mon_pct, days_with_data, total_days, volatility,
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
            "strengths": strengths,
            "weaknesses": weaknesses,
            "profit_killers": killers,
            "trend": trend,
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
