import math
from datetime import date, timedelta
from typing import Dict, Any, List
from sqlalchemy import text
from backend.database import SessionLocal
from backend.routers.metrics import FILTER_OUT_MONETISATION
from backend.services.insight_config_service import get_config_for_source

def run_deep_insight_analysis(source_name: str, days: int = 30) -> Dict[str, Any]:
    """
    Runs the Deep Insight Factory engine for a specific traffic source.
    Builds a dynamic SQL GROUP BY query using only the parameters marked with weight `1` (Core).
    Then applies the user-defined thresholds to categorize them into "Scale" or "Kill".
    """
    config = get_config_for_source(source_name)
    weights = config.get("parameter_weights", {})
    thresholds = config.get("thresholds", {})
    
    scale_min_roi = thresholds.get("scale_min_roi", 20)
    scale_min_profit = thresholds.get("scale_min_profit", 5)
    scale_min_conversions = thresholds.get("scale_min_conversions", 3)
    
    kill_min_spend = thresholds.get("kill_min_spend", 20)
    kill_max_roi = thresholds.get("kill_max_roi", -40)

    # Find the core parameters to group by (weight == 1)
    core_params = [k for k, v in weights.items() if v == 1 and k != "traffic_source"]
    
    if not core_params:
        return {
            "success": False, 
            "error": "No Core parameters (Weight=1) defined for this source.",
            "scale_combos": [],
            "kill_combos": []
        }

    date_from = date.today() - timedelta(days=days)
    
    # Map the JSON keys to actual DB column names
    db_columns = []
    for p in core_params:
        db_columns.append(p)
            
    group_by_clause = ", ".join(db_columns)
    
    # We coalesce parameters to "Unknown" if null, so GROUP BY works cleanly
    select_cols = ", ".join([f"COALESCE({col}, 'Unknown') as {col}" for col in db_columns])
    
    query = f"""
        SELECT 
            {select_cols},
            SUM(cost) as total_cost,
            SUM(revenue) as total_revenue,
            SUM(conversions) as total_conversions,
            COUNT(*) as clicks
        FROM traffic_stats 
        WHERE date >= :date_from 
          AND LOWER(traffic_source) = LOWER(:source)
          {FILTER_OUT_MONETISATION}
        GROUP BY {group_by_clause}
        HAVING SUM(conversions) > 0 OR SUM(cost) > 0
        ORDER BY SUM(revenue) - SUM(cost) DESC
    """
    
    scale_combos = []
    kill_combos = []
    
    with SessionLocal() as db:
        rows = db.execute(text(query), {"date_from": date_from, "source": source_name}).fetchall()
        
        # Determine column indexes
        # Custom columns come first, then cost, revenue, conversions, clicks
        param_count = len(db_columns)
        
        for row in rows:
            combo_values = {}
            for i, col in enumerate(db_columns):
                # The returned value might be empty string or null
                val = str(row[i]).strip() if row[i] is not None else "Unknown"
                if not val:
                    val = "Unknown"
                combo_values[col] = val
                
            spend = float(row[param_count] or 0)
            revenue = float(row[param_count + 1] or 0)
            conversions = int(row[param_count + 2] or 0)
            clicks = int(row[param_count + 3] or 0)
            
            profit = revenue - spend
            roi = (profit / spend * 100) if spend > 0 else 0
            
            combo_name = " + ".join([v for v in combo_values.values() if v != "Unknown"])
            if not combo_name:
                combo_name = "Mixed / Unknown Segments"
                
            combo_data = {
                "combo": combo_values,
                "name": combo_name,
                "spend": round(spend, 2),
                "revenue": round(revenue, 2),
                "profit": round(profit, 2),
                "conversions": conversions,
                "clicks": clicks,
                "roi": round(roi, 1)
            }
            
            # Apply Threshold Rules
            
            # 1. Scale Rule
            if roi >= scale_min_roi and profit >= scale_min_profit and conversions >= scale_min_conversions:
                scale_combos.append(combo_data)
                
            # 2. Kill Rule
            elif spend >= kill_min_spend and (roi <= kill_max_roi or conversions == 0):
                kill_combos.append(combo_data)
                
    return {
        "success": True,
        "source": source_name,
        "days": days,
        "core_parameters": core_params,
        "scale_combos": scale_combos,
        "kill_combos": kill_combos
    }
