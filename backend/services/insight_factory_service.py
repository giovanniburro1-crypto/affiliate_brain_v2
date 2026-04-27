import math
from datetime import date, timedelta
from typing import Dict, Any, List
from sqlalchemy import text
from backend.database import SessionLocal
from backend.services.insight_config_service import get_config_for_source

PARAM_LABELS = {
    "token1": "Token1 (Campaign ID)",
    "token2": "Token2 (Source/Creative)",
    "token3": "Token3",
    "token4": "Token4",
    "token5": "Token5",
    "token6": "Token6",
    "token7": "Token7",
    "token8": "Token8",
    "token9": "Token9",
    "token10": "Token10",
    "offer": "Offer",
    "lander_id": "Lander",
    "os": "OS",
    "device_type": "Device",
    "browser_name": "Browser",
    "country": "Country",
    "language": "Language",
    "rule": "Rule",
    "path": "Path",
    "campaign": "Campaign",
}


def _run_synergy_query(
    source_name: str,
    columns: List[str],
    thresholds: Dict[str, Any],
    date_from: date,
    tier: str = "core"
) -> Dict[str, Any]:
    """
    Internal helper: runs a single GROUP BY synergy query for a set of columns.
    Returns scale_combos, kill_combos, and metadata.
    `tier` is 'core' or 'secondary' — attached to each combo for UI differentiation.
    """
    from backend.routers.metrics import FILTER_OUT_MONETISATION
    
    scale_min_roi = thresholds.get("scale_min_roi", 20)
    scale_min_profit = thresholds.get("scale_min_profit", 5)
    scale_min_conversions = thresholds.get("scale_min_conversions", 3)
    kill_min_spend = thresholds.get("kill_min_spend", 20)
    kill_max_roi = thresholds.get("kill_max_roi", -40)

    # Pre-check which columns ACTUALLY have data (skip 100% NULL)
    usable_columns = []
    with SessionLocal() as db:
        for col in columns:
            check_q = f"""
                SELECT COUNT(*) FROM traffic_stats
                WHERE date >= :date_from
                  AND LOWER(traffic_source) = LOWER(:source)
                  {FILTER_OUT_MONETISATION}
                  AND {col} IS NOT NULL
                  AND TRIM({col}) != ''
                LIMIT 1
            """
            cnt = db.execute(text(check_q), {"date_from": date_from, "source": source_name}).scalar()
            if cnt and cnt > 0:
                usable_columns.append(col)
            else:
                print(f"[InsightFactory] Skipping '{col}' — column is 100% empty for {source_name}")

    if not usable_columns:
        return {
            "usable_columns": [],
            "skipped_columns": columns[:],
            "scale_combos": [],
            "kill_combos": []
        }

    group_by_clause = ", ".join(usable_columns)
    select_cols = ", ".join([f"COALESCE(NULLIF(TRIM({col}), ''), 'Unknown') as {col}" for col in usable_columns])
    
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
        param_count = len(usable_columns)
        
        for row in rows:
            combo_values = {}
            combo_labels = {}
            for i, col in enumerate(usable_columns):
                val = str(row[i]).strip() if row[i] is not None else "Unknown"
                if not val:
                    val = "Unknown"
                combo_values[col] = val
                label = PARAM_LABELS.get(col, col)
                combo_labels[col] = f"{label}: {val}"
                
            spend = float(row[param_count] or 0)
            revenue = float(row[param_count + 1] or 0)
            conversions = int(row[param_count + 2] or 0)
            clicks = int(row[param_count + 3] or 0)
            
            profit = revenue - spend
            roi = (profit / spend * 100) if spend > 0 else 0
            
            name_parts = []
            for col in usable_columns:
                v = combo_values[col]
                if v != "Unknown":
                    label = PARAM_LABELS.get(col, col)
                    name_parts.append(f"{label}: {v}")
            combo_name = " | ".join(name_parts) if name_parts else "Mixed / Unknown Segments"
                
            combo_data = {
                "combo": combo_values,
                "combo_labels": combo_labels,
                "name": combo_name,
                "spend": round(spend, 2),
                "revenue": round(revenue, 2),
                "profit": round(profit, 2),
                "conversions": conversions,
                "clicks": clicks,
                "roi": round(roi, 1),
                "tier": tier
            }
            
            if roi >= scale_min_roi and profit >= scale_min_profit and conversions >= scale_min_conversions:
                scale_combos.append(combo_data)
            elif spend >= kill_min_spend and (roi <= kill_max_roi or conversions == 0):
                kill_combos.append(combo_data)

    return {
        "usable_columns": usable_columns,
        "skipped_columns": [c for c in columns if c not in usable_columns],
        "scale_combos": scale_combos,
        "kill_combos": kill_combos
    }


# Minimum number of combined (scale + kill) insights before triggering fallback
FALLBACK_MIN_INSIGHTS = 2


def run_deep_insight_analysis(source_name: str, days: int = 30) -> Dict[str, Any]:
    """
    Runs the Deep Insight Factory engine for a specific traffic source.
    
    Phase 1 (Core): GROUP BY parameters marked with weight `1`.
    Phase 2 (Fallback): If Core produces fewer than FALLBACK_MIN_INSIGHTS combos,
                        automatically runs a second pass with Secondary (weight=2) params.
    
    Results from both tiers are returned separately so the UI can differentiate them.
    """
    config = get_config_for_source(source_name)
    weights = config.get("parameter_weights", {})
    thresholds = config.get("thresholds", {})
    
    core_params = [k for k, v in weights.items() if v == 1 and k != "traffic_source"]
    secondary_params = [k for k, v in weights.items() if v == 2 and k != "traffic_source"]
    
    if not core_params and not secondary_params:
        return {
            "success": False, 
            "error": "No Core (1) or Secondary (2) parameters defined for this source.",
            "scale_combos": [],
            "kill_combos": []
        }

    date_from = date.today() - timedelta(days=days)
    
    # ---- Phase 1: Core parameters (weight == 1) ----
    core_result = {"usable_columns": [], "skipped_columns": [], "scale_combos": [], "kill_combos": []}
    if core_params:
        core_result = _run_synergy_query(source_name, core_params, thresholds, date_from, tier="core")
    
    core_total = len(core_result["scale_combos"]) + len(core_result["kill_combos"])
    
    # ---- Phase 2: Fallback to Secondary (weight == 2) if insights are lacking ----
    fallback_used = False
    secondary_result = {"usable_columns": [], "skipped_columns": [], "scale_combos": [], "kill_combos": []}
    
    if core_total < FALLBACK_MIN_INSIGHTS and secondary_params:
        print(f"[InsightFactory] Core produced only {core_total} insights — activating Secondary fallback for '{source_name}'")
        secondary_result = _run_synergy_query(source_name, secondary_params, thresholds, date_from, tier="secondary")
        fallback_used = True
    
    # ---- Merge results (core first, then secondary) ----
    all_scale = core_result["scale_combos"] + secondary_result["scale_combos"]
    all_kill = core_result["kill_combos"] + secondary_result["kill_combos"]
    
    # Sort: core tier first, then by profit descending
    tier_order = {"core": 0, "secondary": 1}
    all_scale.sort(key=lambda x: (tier_order.get(x.get("tier", "core"), 1), -x["profit"]))
    all_kill.sort(key=lambda x: (tier_order.get(x.get("tier", "core"), 1), x["profit"]))
    
    # Build response
    all_usable = core_result["usable_columns"] + secondary_result["usable_columns"]
    all_skipped = core_result["skipped_columns"] + secondary_result["skipped_columns"]
    
    if not all_usable and not core_params:
        return {
            "success": False, 
            "error": "No Core (1) parameters defined. Configure at least one Core parameter in Settings.",
            "scale_combos": [],
            "kill_combos": []
        }
    
    if not all_usable:
        return {
            "success": False, 
            "error": f"All parameters are empty in the database for '{source_name}'. Check your data import.", 
            "scale_combos": [],
            "kill_combos": [],
            "skipped_columns": all_skipped
        }
    
    return {
        "success": True,
        "source": source_name,
        "days": days,
        "core_parameters": core_params,
        "secondary_parameters": secondary_params,
        "usable_columns": all_usable,
        "skipped_columns": all_skipped,
        "fallback_used": fallback_used,
        "core_insights_count": core_total,
        "secondary_insights_count": len(secondary_result["scale_combos"]) + len(secondary_result["kill_combos"]),
        "scale_combos": all_scale,
        "kill_combos": all_kill
    }

def get_factory_opportunities(breakdown: Dict[str, Any], source_name: str) -> List[Dict[str, Any]]:
    """
    Cross-analysis Opportunity Engine.
    Finds if the current campaign has parameters that are part of global Scale combos
    in the Insight Factory. Returns Pivot and Validation recommendations.
    """
    if not source_name:
        return []
        
    # 1. Собрать все параметры из текущей кампании
    current_params = {}
    
    # Custom mappings from insight config names to metrics.py dimension names
    key_mapping = {
        "offer": "by_offer_id",
        "lander_id": "by_lander_id_jump",
        "device_type": "by_device_type",
        "browser_name": "by_browser_name",
        "os": "by_os",
        "country": "by_country",
        "language": "by_language",
        "rule": "by_rule",
        "path": "by_path"
    }

    for param, values_list in breakdown.items():
        if isinstance(values_list, list) and param not in ["summary", "path_offer_lander", "daily_metrics",
                                                            "top_combinations_token2_offer_id_jump"]:
            s = set()
            for v in values_list:
                for dict_k, dict_v in v.items():
                    if dict_k not in ["spend", "revenue", "conversions", "clicks", "epc", "cr_pct", "profit"]:
                        val = str(dict_v).strip()
                        if val and val != "None" and val != "(empty)":
                            s.add(val)
            if s:
                current_params[param] = s

    # Metrics router doesn't group by token1 because it's usually campaign_id
    if "by_token1" not in current_params:
        cid = breakdown.get("summary", {}).get("campaign_id")
        if cid:
            current_params["by_token1"] = {str(cid)}
            
    # 2. Получить Scale-связки из Фабрики
    try:
        factory_data = run_deep_insight_analysis(source_name, days=30)
    except Exception as e:
        print(f"Factory Error: {e}")
        return []
        
    if not factory_data.get("success"):
        return []
        
    scale_combos = factory_data.get("scale_combos", [])
    recommendations = []
    
    for item in scale_combos:
        combo = item["combo"]
        roi = item.get("roi", 0)
        profit = item.get("profit", 0)
        conversions = item.get("conversions", 0)
        spend = item.get("spend", 0)
        
        # Найти пересечения (что общего) и разрывы (что отличается)
        matches = []
        missing = []
        
        for p_name, p_value in combo.items():
            if p_value == "Unknown" or not p_value:
                continue
                
            p_val_str = str(p_value).strip()
            label = PARAM_LABELS.get(p_name, p_name)
            
            mapped_key = f"by_{p_name}"
            if p_name in key_mapping:
                mapped_key = key_mapping[p_name]
                
            if mapped_key in current_params and p_val_str in current_params.get(mapped_key, set()):
                matches.append({"param": p_name, "label": label, "value": p_value})
            else:
                missing.append({"param": p_name, "label": label, "value": p_value})
                
        # Build readable strings
        match_strs = [f"{m['label']}: {m['value']}" for m in matches]
        missing_strs = [f"{m['label']}: {m['value']}" for m in missing]
        
        # Если есть хотя бы одно совпадение И хотя бы один отличный параметр -> это Pivot!
        if matches and missing:
            rec = {
                "type": "PIVOT",
                "message": f"Ваш параметр ({', '.join(match_strs)}) глобально приносит лучший ROI с {', '.join(missing_strs)}. Рекомендуем затестить эту связку!",
                "roi": roi,
                "profit": profit,
                "conversions": conversions,
                "spend": spend,
                "combo": item["name"],
                "missing_params": missing_strs,
                "matched_params": match_strs
            }
            recommendations.append(rec)
        elif matches and not missing:
            rec = {
                "type": "VALIDATION",
                "message": f"Связка ({', '.join(match_strs)}) в топе по всему источнику! ROI {roi}%, Profit ${profit}. Масштабируйте!",
                "roi": roi,
                "profit": profit,
                "conversions": conversions,
                "spend": spend,
                "combo": item["name"],
                "missing_params": [],
                "matched_params": match_strs
            }
            recommendations.append(rec)
            
    # Sort by profit
    recommendations.sort(key=lambda x: x["profit"], reverse=True)
    return recommendations[:10]  # Top 10 opportunities

