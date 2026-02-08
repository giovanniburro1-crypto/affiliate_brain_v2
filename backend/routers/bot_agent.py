"""
TOP-5 Bot Agent — API для отбора кампаний на масштабирование.
Использует Top5Service (волатильность, сегменты, 4-6 строк).
"""
from datetime import date, timedelta, datetime
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

from backend.database import get_db
from backend.models import AIMemory
from backend.services.top5_service import Top5Service

router = APIRouter()
CONFIDENCE_THRESHOLD = 95


class ApplyBody(BaseModel):
    campaign_id: str
    verdict: str
    hide_days: int = 0
    confidence: float = 0


def _period_or_range(
    period: int,
    date_from_str: Optional[str],
    date_to_str: Optional[str],
) -> tuple:
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


@router.get("/top5")
async def get_top5(
    period: int = Query(30),
    date_from_param: Optional[str] = Query(None, alias="date_from"),
    date_to_param: Optional[str] = Query(None, alias="date_to"),
    db: Session = Depends(get_db),
):
    """TOP-5 кампаний с полным форматом 4-6 строк (сила + слабость)."""
    service = Top5Service(db)
    result = service.get_top5(
        period=period,
        date_from_str=date_from_param,
        date_to_str=date_to_param,
        limit=5,
    )
    return result


@router.post("/analyze")
async def analyze(
    campaign_id: str = Query(...),
    period: int = Query(7),
    db: Session = Depends(get_db),
):
    """Анализ одной кампании."""
    service = Top5Service(db)
    c = service.get_campaign_analysis(
        campaign_id=campaign_id,
        period=period,
    )
    if not c:
        return {"error": "Not found"}
    try:
        db.add(
            AIMemory(
                campaign_id=c["campaign_id"],
                decision_date=datetime.now(),
                bot_verdict=c["verdict"],
                bot_score=c["bot_score"],
                bot_confidence=c["confidence"],
                bot_reasoning="; ".join(c.get("summary_lines", [])),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
    return {
        "campaign_id": c["campaign_id"],
        "campaign": c["campaign"],
        "source": c["source"],
        "spend": c["spend"],
        "revenue": c["revenue"],
        "profit": c["profit"],
        "roi": c["roi"],
        "conversions": c["conversions"],
        "clicks": c["clicks"],
        "verdict": c["verdict"],
        "bot_score": c["bot_score"],
        "confidence": c["confidence"],
        "reasoning": "; ".join(c.get("summary_lines", [])),
        "volatility": c["volatility"],
    }


@router.post("/apply")
async def apply(body: ApplyBody, db: Session = Depends(get_db)):
    """Применить вердикт при уверенности ≥95%."""
    if body.confidence < CONFIDENCE_THRESHOLD:
        return {
            "success": False,
            "error": f"Применить можно только при уверенности ≥{CONFIDENCE_THRESHOLD}%. Сейчас: {round(body.confidence)}%.",
        }
    date_from = date.today() - timedelta(days=14)
    date_to = date.today()
    row = db.execute(
        text("""
            SELECT campaign, traffic_source, SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
            FROM traffic_stats
            WHERE campaign_id = :c AND date >= :d AND date <= :d_to
            GROUP BY campaign, traffic_source
        """),
        {"c": body.campaign_id, "d": date_from, "d_to": date_to},
    ).fetchone()
    if not row:
        return {"success": False, "error": "Кампания не найдена"}
    spend = int(round(float(row[2] or 0)))
    revenue = int(round(float(row[3] or 0)))
    conversions = int(row[4] or 0)
    profit = revenue - spend
    roi = round((profit / spend * 100) if spend > 0 else 0)
    verdict = (body.verdict or "HOLD").upper()
    if verdict not in ("SCALE", "HOLD", "OPTIMIZE", "STOP"):
        verdict = "HOLD"
    try:
        db.add(
            AIMemory(
                campaign_id=body.campaign_id,
                decision_date=datetime.now(),
                bot_verdict=verdict,
                bot_score=0,
                bot_confidence=body.confidence,
                bot_reasoning=f"Applied: {verdict}",
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        return {"success": False, "error": "Ошибка записи в БД"}
    return {"success": True}
