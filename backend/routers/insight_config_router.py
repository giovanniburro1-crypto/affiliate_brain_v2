from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any

from backend.services.insight_config_service import (
    get_all_configs,
    get_config_for_source,
    save_config_for_source,
    delete_config_for_source,
    DEFAULT_TEMPLATE
)
from backend.services.insight_factory_service import run_deep_insight_analysis

router = APIRouter()

class InsightConfigUpdate(BaseModel):
    parameter_weights: Dict[str, int]
    thresholds: Dict[str, float]

@router.get("/insight-configs")
def get_configs():
    """Returns all traffic source templates"""
    configs = get_all_configs()
    return {"success": True, "configs": configs, "default_template": DEFAULT_TEMPLATE}

@router.get("/insight-configs/{source_name}")
def get_source_config(source_name: str):
    """Returns exactly one template for a given source"""
    config = get_config_for_source(source_name)
    return {"success": True, "config": config}

@router.post("/insight-configs/{source_name}")
def update_source_config(source_name: str, payload: InsightConfigUpdate):
    """Saves a modified template for a traffic source"""
    try:
        updated_configs = save_config_for_source(source_name, payload.model_dump())
        return {"success": True, "configs": updated_configs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/insight-configs/{source_name}")
def delete_source_config(source_name: str):
    """Deletes a template for a traffic source, except default"""
    try:
        updated_configs = delete_config_for_source(source_name)
        return {"success": True, "configs": updated_configs}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/insight-configs/{source_name}/run")
def run_insight_factory(source_name: str, days: int = 30):
    """Runs the Deep Insight Factory Engine for a given traffic source."""
    try:
        result = run_deep_insight_analysis(source_name, days)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
