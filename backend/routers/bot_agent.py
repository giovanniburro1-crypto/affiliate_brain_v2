"""
TOP-5 Bot Agent — API для отбора кампаний на масштабирование.
Использует Top5Service (волатильность, сегменты, 4-6 строк).
"""
import json
import os
from datetime import date, timedelta, datetime
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

# #region agent log
_DEBUG_LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", ".cursor", "debug.log")
def _debug_log(location: str, message: str, data: dict, hypothesis_id: str = ""):
    try:
        payload = {"location": location, "message": message, "data": data, "timestamp": datetime.utcnow().isoformat() + "Z"}
        if hypothesis_id:
            payload["hypothesisId"] = hypothesis_id
        with open(_DEBUG_LOG_PATH, "a") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
# #endregion

from backend.database import get_db
from backend.models import AIMemory, RecheckQueue
from backend.services.top5_service import Top5Service

router = APIRouter()
CONFIDENCE_THRESHOLD = 95


class ApplyBody(BaseModel):
    campaign_id: str
    verdict: str
    hide_days: int = 0  # legacy, map to recheck_after_days
    recheck_after_days: int = 0  # 0 = некогда, 1/2/3/5/7 = add to queue
    confidence: float = 0


RECHECK_QUEUE_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS recheck_queue (
    id SERIAL PRIMARY KEY,
    campaign_id VARCHAR(100) NOT NULL,
    campaign VARCHAR(255),
    verdict VARCHAR(50),
    recheck_after_days INTEGER DEFAULT 0,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def _ensure_recheck_queue_table(db: Session) -> None:
    """Создать таблицу recheck_queue при первом обращении, если её нет."""
    # #region agent log
    _debug_log("bot_agent:_ensure_recheck_queue_table:entry", "ensure table entry", {}, "H1")
    # #endregion
    try:
        # #region agent log
        _debug_log("bot_agent:_ensure_recheck_queue_table:before_execute", "executing CREATE TABLE", {"sql_preview": RECHECK_QUEUE_CREATE_SQL[:80]}, "H2")
        # #endregion
        db.execute(text(RECHECK_QUEUE_CREATE_SQL))
        # #region agent log
        _debug_log("bot_agent:_ensure_recheck_queue_table:after_execute", "execute done, committing", {}, "H2")
        # #endregion
        db.commit()
        # #region agent log
        _debug_log("bot_agent:_ensure_recheck_queue_table:after_commit", "commit done", {}, "H2")
        # #endregion
    except Exception as e:
        # #region agent log
        _debug_log("bot_agent:_ensure_recheck_queue_table:exception", "ensure failed", {"error": str(e), "type": type(e).__name__}, "H4")
        # #endregion
        db.rollback()
        raise


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


@router.get("/recheck-queue")
async def get_recheck_queue(db: Session = Depends(get_db)):
    """Очередь речека: все записи, сортировка по recheck_due_date (сначала «речек сегодня»)."""
    try:
        _ensure_recheck_queue_table(db)
    except Exception:
        return []
    try:
        rows = db.execute(
            text("SELECT id, campaign_id, campaign, verdict, recheck_after_days, applied_at FROM recheck_queue")
        ).fetchall()
    except Exception:
        return []
    today = date.today()
    result = []
    for r in rows:
        rid, cid, campaign, verdict, days, applied_at = r
        if hasattr(applied_at, "date"):
            applied_date = applied_at.date()
        else:
            applied_date = applied_at if isinstance(applied_at, date) else today
        recheck_due = applied_date + timedelta(days=days or 0)
        days_ago = (today - applied_date).days
        result.append({
            "id": rid,
            "campaign_id": cid,
            "campaign": campaign or cid,
            "verdict": verdict or "HOLD",
            "recheck_after_days": days,
            "applied_at": applied_at.isoformat() if hasattr(applied_at, "isoformat") else str(applied_at),
            "recheck_due_date": recheck_due.isoformat(),
            "days_ago": days_ago,
        })
    result.sort(key=lambda x: (x["recheck_due_date"], x["days_ago"]))
    return result


@router.get("/campaign-analysis")
async def get_campaign_analysis(
    campaign_id: str = Query(...),
    period: int = Query(7),
    date_from_param: Optional[str] = Query(None, alias="date_from"),
    date_to_param: Optional[str] = Query(None, alias="date_to"),
    db: Session = Depends(get_db),
):
    """Read-only анализ кампании за период (без записи в AIMemory)."""
    service = Top5Service(db)
    c = service.get_campaign_analysis(
        campaign_id=campaign_id,
        period=period,
        date_from_str=date_from_param,
        date_to_str=date_to_param,
    )
    if not c:
        return {"error": "Not found"}
    return c


@router.delete("/recheck-queue/{item_id}")
async def delete_recheck_queue_item(item_id: int, db: Session = Depends(get_db)):
    """Удалить запись из очереди речека."""
    try:
        _ensure_recheck_queue_table(db)
    except Exception:
        return {"success": False, "error": "Ошибка создания таблицы очереди"}
    db.execute(text("DELETE FROM recheck_queue WHERE id = :id"), {"id": item_id})
    db.commit()
    return {"success": True}


@router.post("/apply")
async def apply(body: ApplyBody, db: Session = Depends(get_db)):
    """Применить вердикт пользователя: всегда пишем в AIMemory и при выборе речека — в очередь. Уверенность бота не ограничивает действие."""
    recheck_days = getattr(body, "recheck_after_days", None)
    if recheck_days is None and getattr(body, "hide_days", None) is not None:
        recheck_days = body.hide_days
    recheck_days = recheck_days if recheck_days is not None else 0
    recheck_days = int(recheck_days)

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

    if recheck_days in (1, 2, 3, 5, 7):
        # #region agent log
        _debug_log("bot_agent:apply:recheck_branch", "entering recheck branch", {"recheck_days": recheck_days, "campaign_id": body.campaign_id}, "H1")
        # #endregion
        try:
            _ensure_recheck_queue_table(db)
            # #region agent log
            _debug_log("bot_agent:apply:after_ensure", "ensure returned without exception", {}, "H1")
            # #endregion
        except Exception as e:
            return {"success": False, "error": f"Ошибка создания таблицы очереди: {e}"}
        campaign_name = row[0] or body.campaign_id
        # #region agent log
        _debug_log("bot_agent:apply:before_select", "about to SELECT from recheck_queue", {"campaign_id": body.campaign_id}, "H5")
        # #endregion
        existing = db.execute(
            text("SELECT id FROM recheck_queue WHERE campaign_id = :c"),
            {"c": body.campaign_id},
        ).fetchone()
        if existing:
            db.execute(
                text("""
                    UPDATE recheck_queue
                    SET campaign = :campaign, verdict = :verdict, recheck_after_days = :days, applied_at = :now
                    WHERE campaign_id = :c
                """),
                {
                    "campaign": campaign_name,
                    "verdict": verdict,
                    "days": recheck_days,
                    "now": datetime.now(),
                    "c": body.campaign_id,
                },
            )
            db.commit()
        else:
            db.add(
                RecheckQueue(
                    campaign_id=body.campaign_id,
                    campaign=campaign_name,
                    verdict=verdict,
                    recheck_after_days=recheck_days,
                )
            )
            db.commit()

    message = "Добавлено в очередь речека." if recheck_days in (1, 2, 3, 5, 7) else "Применено."
    return {"success": True, "message": message}
