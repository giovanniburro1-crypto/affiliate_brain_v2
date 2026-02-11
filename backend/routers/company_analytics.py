"""
Company Analytics — полный анализ кампании с использованием Logic_Blocks (Brain).
Используется на странице Company Analysis. Logic_Blocks обновляется отдельно.
"""
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.brain import KnowledgeBase
from backend.services.top5_service import Top5Service
from backend.services.campaign_analysis_service import get_parameter_conclusions
from backend.routers.metrics import get_campaign_breakdown_data, get_campaign_daily_days

router = APIRouter()


@router.get("/company-analytics/analysis")
async def get_company_analysis(
    campaign_id: str = Query(..., description="Campaign ID"),
    period: int = Query(14),
    date_from_param: Optional[str] = Query(None, alias="date_from"),
    date_to_param: Optional[str] = Query(None, alias="date_to"),
    source: Optional[str] = Query(None, description="Traffic source filter"),
    db: Session = Depends(get_db),
):
    """
    Полный анализ кампании для страницы Company Analytics.
    Объединяет: Top5Service (сегменты, волатильность, 4-6 строк) + Brain (правила, паттерны)
    + выводы по 26 параметрам.
    """
    brain = KnowledgeBase()
    service = Top5Service(db, brain)

    today = date.today()
    if date_from_param and date_to_param:
        try:
            d_from = date.fromisoformat(date_from_param.strip()[:10])
            d_to = date.fromisoformat(date_to_param.strip()[:10])
            if d_from <= d_to:
                date_from, date_to = d_from, d_to
            else:
                date_from, date_to = today - timedelta(days=period), today
        except (ValueError, TypeError):
            date_from, date_to = today - timedelta(days=period), today
    else:
        date_from, date_to = today - timedelta(days=period), today

    # Анализ кампании через Top5Service
    analysis = service.get_campaign_analysis(
        campaign_id=campaign_id,
        period=period,
        date_from_str=date_from.isoformat(),
        date_to_str=date_to.isoformat(),
    )
    if not analysis:
        return {"success": False, "error": "Campaign not found"}

    # Breakdown и выводы по 26 параметрам
    breakdown = get_campaign_breakdown_data(db, campaign_id, date_from, date_to)
    # Динамика по дням (days[MM-DD] = {profit, color})
    daily_days = get_campaign_daily_days(db, campaign_id, date_from, date_to, source)
    volatility = analysis.get("volatility", 0) or 0
    parameter_conclusions = get_parameter_conclusions(
        breakdown=breakdown,
        campaign_summary=breakdown.get("summary", {}),
        volatility=volatility,
        brain=brain,
    )

    # Знания из Brain (Logic_Blocks)
    core_rules = brain.get_core_rules()
    killer_rules = brain.get_killer_rules()
    zacep_rules = brain.get_zacep_rules()
    winning_combos = brain.get_winning_combos()
    killer_patterns = brain.get_killer_patterns()
    segment_columns = brain.get_segment_columns(analysis.get("source"))

    return {
        "success": True,
        "campaign_id": campaign_id,
        "analysis": analysis,
        "parameter_conclusions": parameter_conclusions,
        "breakdown": breakdown,
        "days": daily_days,
        "brain": {
            "core_rules": core_rules,
            "killer_rules": killer_rules,
            "zacep_rules": zacep_rules,
            "winning_combos_count": len(winning_combos),
            "killer_patterns_count": len(killer_patterns),
            "segment_columns": segment_columns,
        },
    }


@router.get("/company-analytics/segment-config")
async def get_segment_config():
    """Конфиг колонок для сегментации по traffic source."""
    brain = KnowledgeBase()
    data = brain.get_segment_config_raw()
    return {"success": True, "config": data}
