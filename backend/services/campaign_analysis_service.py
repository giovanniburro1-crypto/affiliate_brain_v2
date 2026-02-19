"""
Campaign Analysis Service — выводы бота по 26 параметрам.
Rule-based анализ на основе breakdown и правил из logic_blocks.
"""
from typing import Any, Dict, List, Optional
from backend.brain import KnowledgeBase


def _best_worst(items: List[Dict], profit_key: str = "profit") -> tuple:
    """Возвращает (best, worst) из отсортированного по profit списка."""
    if not items:
        return None, None
    sorted_items = sorted(items, key=lambda x: x.get(profit_key, 0) or 0, reverse=True)
    best = sorted_items[0] if sorted_items else None
    worst = sorted_items[-1] if len(sorted_items) > 1 else None
    return best, worst


def _format_conclusion(
    param: str,
    best: Optional[Dict],
    worst: Optional[Dict],
    name_key: str = "name",
) -> str:
    """Форматирует короткий вывод: что работает, что нет."""
    parts = []
    if best:
        name = best.get(name_key, best.get("offer_id", best.get("lander_id", "—")))
        prof = best.get("profit", 0)
        parts.append(f"Топ: {name} (profit ${prof})")
    if worst and worst != best:
        name = worst.get(name_key, worst.get("offer_id", best.get("lander_id", "—")))
        prof = worst.get("profit", 0)
        parts.append(f"Худший: {name} (profit ${prof})")
    return "; ".join(parts) if parts else "Недостаточно данных"


def get_parameter_conclusions(
    breakdown: Dict[str, Any],
    campaign_summary: Dict[str, Any],
    volatility: float = 0,
    brain: Optional[KnowledgeBase] = None,
) -> Dict[str, Dict[str, Any]]:
    """Генерирует выводы по каждому из 26 параметров."""
    brain = brain or KnowledgeBase()
    conclusions: Dict[str, Dict[str, Any]] = {}

    summary = breakdown.get("summary") or campaign_summary
    spend = summary.get("spend", 0) or 0
    revenue = summary.get("revenue", 0) or 0
    conversions = summary.get("conversions", 0) or 0
    cr_pct = summary.get("cr_pct", 0) or 0

    # Date Click, Campaign ID, Traffic Source, Payout, Conversion, Cost
    vol_label = "высокая" if volatility > 30 else ("средняя" if volatility > 15 else "низкая")
    conclusions["date_click"] = {
        "metrics": {"volatility": round(volatility, 2)},
        "conclusion": f"Волатильность {vol_label} ({volatility:.1f}). {'Рекомендуется стабилизировать перед скейлом.' if volatility > 25 else 'Подходит для тестирования.'}",
    }
    conclusions["campaign_id"] = {"metrics": {}, "conclusion": "Идентификатор кампании. Анализ не применим."}
    conclusions["traffic_source"] = {"metrics": {}, "conclusion": "Источник трафика. Используется для фильтрации кампаний."}
    conclusions["payout"] = {"metrics": {"revenue": revenue}, "conclusion": f"Payout ${revenue}. {'Низкий при таком spend.' if spend > 0 and revenue / spend < 0.5 else 'В норме.'}"}
    conclusions["conversion"] = {"metrics": {"conversions": conversions, "cr_pct": cr_pct}, "conclusion": f"{conversions} конверсий, CR {cr_pct}%. {'Мало конверсий для выводов.' if conversions < 3 else 'Достаточно данных.'}"}
    conclusions["cost"] = {"metrics": {"spend": spend}, "conclusion": f"Spend ${spend}. {'Достаточно для анализа.' if spend >= 20 else 'Мало данных (min $20).'}"}

    # Все остальные параметры
    params = [
        ("path", "by_path", "path"),
        ("rule", "by_rule", "rule"),
        ("offer_id", "by_offer_id", "offer_id"),
        ("lander_id", "by_lander_id_jump", "lander_id"),
        ("device_type", "by_device_type", "device_type"),
        ("country", "by_country", "name"),
        ("os", "by_os", "os"),
        ("os_version", "by_os_version", "os_version"),
        ("browser_name", "by_browser_name", "browser_name"),
        ("language", "by_language", "language"),
        ("token2", "by_token2", "name"),
    ]
    
    for i in range(3, 11):
        params.append((f"token{i}", f"by_token{i}", f"token{i}"))

    for key, source_key, name_key in params:
        if key == "lander_id":
            items = breakdown.get("by_lander_id_jump") or breakdown.get("by_lander_id") or []
        else:
            items = breakdown.get(source_key) or []
        
        best, worst = _best_worst(items)
        conclusions[key] = {
            "metrics": {"count": len(items)},
            "conclusion": _format_conclusion(key, best, worst, name_key=name_key) if items else f"Нет разбивки по {key}."
        }

    conclusions["token1"] = {"metrics": {}, "conclusion": "Token1 = Campaign ID. Без отдельного анализа."}
    
    return conclusions


def get_bot_actions(
    analysis: Dict[str, Any],
    path_offer_lander: List[Dict[str, Any]],
    breakdown: Dict[str, Any],
    brain: Optional[KnowledgeBase] = None,
) -> List[Dict[str, Any]]:
    """
    ACTION PLAN - Генерирует конкретные действия на основе анализа ВСЕХ 26 параметров.
    
    Логика:
    1. KILL - сегменты с критическими потерями (2x payout без конв, ROI < -20%)
    2. ISOLATE - победители (zacep: 3+ конв, профит, стабильно)  
    3. OPTIMIZE - проблемные сегменты (низкий EPC, высокий CPA)
    4. SCALE - готовые к масштабированию (ROI > 30%, 3+ конв, 3+ дня)
    """
    brain = brain or KnowledgeBase()
    core_rules = brain.get_core_rules()
    
    killer_rules = core_rules.get("killer_rules", {})
    zacep_rules = core_rules.get("zacep_rules", {})
    optimizer_rules = core_rules.get("optimizer_rules", {})
    scaler_rules = core_rules.get("scaler_rules", {})
    
    actions = []
    
    # === 1. АНАЛИЗ ВСЕХ 26 ПАРАМЕТРОВ ИЗ BREAKDOWN ===
    
    # Получаем segment_config для этого источника
    segment_columns = brain.get_segment_columns(analysis.get("source", "default"))
    
    # Проходим по всем токенам и параметрам
    token_params = [f"by_token{i}" for i in range(2, 11)]
    other_params = ["by_offer_id", "by_lander_id_jump", "by_path", "by_rule", 
                   "by_os", "by_device_type", "by_country", "by_os_version", 
                   "by_browser_name", "by_language"]
    
    all_params = token_params + other_params
    
    for param_key in all_params:
        items = breakdown.get(param_key, [])
        if not items or len(items) <= 1:
            continue
            
        # Сортируем по профиту
        sorted_items = sorted(items, key=lambda x: x.get("profit", 0) or 0, reverse=True)
        best = sorted_items[0]
        worst = sorted_items[-1]
        
        best_profit = best.get("profit", 0) or 0
        worst_profit = worst.get("profit", 0) or 0
        
        # Определяем имя параметра
        param_name = param_key.replace("by_", "").replace("_jump", "")
        name_key = param_name if param_name.startswith("token") else (
            "name" if param_key in ["by_token2", "by_country"] else 
            "lander_id" if "lander" in param_key else
            "offer_id" if param_key == "by_offer_id" else param_name
        )
        
        best_value = best.get(name_key) or best.get("name") or "(empty)"
        worst_value = worst.get(name_key) or worst.get("name") or "(empty)"
        
        # === KILLER LOGIC ===
        # Если сегмент убил > 20% от общего spend с профитом < -$10
        total_spend = analysis.get("spend", 0) or 0
        worst_spend = worst.get("spend", 0) or 0
        worst_conversions = worst.get("conversions", 0) or 0
        
        if total_spend > 0:
            worst_spend_pct = (worst_spend / total_spend) * 100
            
            # Правило: убил > 15% бюджета И профит < -$10 И 0 конверсий
            if worst_spend_pct > 15 and worst_profit < -10 and worst_conversions == 0:
                actions.append({
                    "type": "kill",
                    "param": param_name.upper(),
                    "value": str(worst_value),
                    "text": f"⛔ KILL {param_name.upper()}: {worst_value}",
                    "reason": f"Сжег ${abs(worst_profit):.0f} ({worst_spend_pct:.0f}% бюджета) без конверсий",
                    "confidence": "HIGH"
                })
            
            # Если просто минусит > $10 но есть конверсии
            elif worst_profit < -10 and worst_spend_pct > 10:
                actions.append({
                    "type": "optimize",
                    "param": param_name.upper(),
                    "value": str(worst_value),
                    "text": f"📉 OPTIMIZE {param_name.upper()}: {worst_value}",
                    "reason": f"Минус ${abs(worst_profit):.0f} ({worst_spend_pct:.0f}% бюджета). Снизить бид или отключить.",
                    "confidence": "MEDIUM"
                })
        
        # === WINNER LOGIC (ISOLATE) ===
        best_conversions = best.get("conversions", 0) or 0
        best_roi = best.get("roi", 0) or 0
        
        # Правило: профит > $5, есть конверсии, но ROI < 30% (потенциал для изоляции)
        if best_profit > 5 and best_conversions >= zacep_rules.get("min_conversions", 3):
            if best_roi > 0 and best_roi < scaler_rules.get("min_roi", 30):
                actions.append({
                    "type": "isolate",
                    "param": param_name.upper(),
                    "value": str(best_value),
                    "text": f"💎 ISOLATE {param_name.upper()}: {best_value}",
                    "reason": f"Профит +${best_profit:.0f}, {best_conversions} конв, ROI {best_roi:.0f}%. Вынести в отдельный path.",
                    "confidence": "HIGH"
                })
            
            # Правило: готов к SCALE (ROI > 30%, конв >= 3)
            elif best_roi >= scaler_rules.get("min_roi", 30) and best_conversions >= scaler_rules.get("min_conversions", 3):
                actions.append({
                    "type": "scale",
                    "param": param_name.upper(),
                    "value": str(best_value),
                    "text": f"🚀 SCALE {param_name.upper()}: {best_value}",
                    "reason": f"ROI {best_roi:.0f}%, {best_conversions} конв, профит +${best_profit:.0f}. Увеличить бюджет.",
                    "confidence": "HIGH"
                })
    
    # === 2. ОБЩИЙ АНАЛИЗ КАМПАНИИ ===
    campaign_roi = analysis.get("roi", 0) or 0
    campaign_conversions = analysis.get("conversions", 0) or 0
    campaign_profit = analysis.get("profit", 0) or 0
    
    # Если кампания в целом убыточна (ROI < -20%)
    if campaign_roi < killer_rules.get("roi_threshold", -20):
        actions.append({
            "type": "kill",
            "param": "CAMPAIGN",
            "value": analysis.get("campaign_id", ""),
            "text": "⛔ STOP CAMPAIGN",
            "reason": f"ROI {campaign_roi:.0f}% < {killer_rules.get('roi_threshold', -20)}%. Критические потери.",
            "confidence": "CRITICAL"
        })
    
    # Если вообще нет конверсий при spend > $50
    if campaign_conversions == 0 and analysis.get("spend", 0) > 50:
        actions.append({
            "type": "kill",
            "param": "CAMPAIGN",
            "value": analysis.get("campaign_id", ""),
            "text": "⛔ STOP CAMPAIGN",
            "reason": "0 конверсий при spend > $50. Слив бюджета.",
            "confidence": "CRITICAL"
        })
    
    # === 3. СОРТИРОВКА ДЕЙСТВИЙ ПО ПРИОРИТЕТУ ===
    # KILL > SCALE > ISOLATE > OPTIMIZE
    priority = {"kill": 1, "scale": 2, "isolate": 3, "optimize": 4}
    actions.sort(key=lambda x: priority.get(x.get("type"), 999))
    
    return actions