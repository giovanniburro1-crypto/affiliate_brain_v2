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
    if best and best.get("profit", 0) > 0:
        name = best.get(name_key, best.get("offer_id", best.get("lander_id", "—")))
        parts.append(f"Лучший: {name} (profit ${best.get('profit', 0)})")
    if worst and worst.get("profit", 0) < 0 and worst != best:
        name = worst.get(name_key, worst.get("offer_id", worst.get("lander_id", "—")))
        parts.append(f"Слабый: {name} (profit ${worst.get('profit', 0)})")
    return "; ".join(parts) if parts else "Недостаточно данных"


def get_parameter_conclusions(
    breakdown: Dict[str, Any],
    campaign_summary: Dict[str, Any],
    volatility: float = 0,
    brain: Optional[KnowledgeBase] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Генерирует выводы по каждому из 26 параметров.
    breakdown: результат campaign-breakdown (by_token2, by_offer_id, by_lander_id, by_os, by_country, by_device_type, summary).
    campaign_summary: spend, revenue, profit, roi, conversions, clicks, epc, cr_pct.
    """
    brain = brain or KnowledgeBase()
    core = brain.get_core_rules()
    conclusions: Dict[str, Dict[str, Any]] = {}

    summary = breakdown.get("summary") or campaign_summary
    spend = summary.get("spend", 0) or 0
    revenue = summary.get("revenue", 0) or 0
    profit = summary.get("profit", 0) or 0
    roi = summary.get("roi", 0) or 0
    conversions = summary.get("conversions", 0) or 0
    clicks = summary.get("clicks", 0) or 0
    epc = summary.get("epc", 0) or 0
    cr_pct = summary.get("cr_pct", 0) or 0

    # 1. Date Click → volatility
    vol_label = "высокая" if volatility > 30 else ("средняя" if volatility > 15 else "низкая")
    conclusions["date_click"] = {
        "metrics": {"volatility": round(volatility, 2)},
        "conclusion": f"Волатильность {vol_label} ({volatility:.1f}). {'Рекомендуется стабилизировать перед скейлом.' if volatility > 25 else 'Подходит для тестирования.'}",
    }

    # 2. Campaign ID — только для имени
    conclusions["campaign_id"] = {
        "metrics": {},
        "conclusion": "Идентификатор кампании. Анализ не применим.",
    }

    # 3. Path
    by_path = breakdown.get("by_path") or []
    best_path, worst_path = _best_worst(by_path)
    conclusions["path"] = {
        "metrics": {"count": len(by_path)},
        "conclusion": _format_conclusion("path", best_path, worst_path, name_key="path") if by_path else "Нет разбивки по Path.",
    }

    # 4. Rule
    by_rule = breakdown.get("by_rule") or []
    best_rule, worst_rule = _best_worst(by_rule)
    conclusions["rule"] = {
        "metrics": {"count": len(by_rule)},
        "conclusion": _format_conclusion("rule", best_rule, worst_rule, name_key="rule") if by_rule else "Нет разбивки по Rule.",
    }

    # 5–6. Offer ID, Lander ID
    by_offer = breakdown.get("by_offer_id") or []
    best_offer, worst_offer = _best_worst(by_offer)
    conclusions["offer_id"] = {
        "metrics": {"count": len(by_offer)},
        "conclusion": _format_conclusion("offer", best_offer, worst_offer, name_key="offer_id") if by_offer else "Нет разбивки по Offer.",
    }

    by_lander = breakdown.get("by_lander_id_jump") or breakdown.get("by_lander_id") or []
    best_lander, worst_lander = _best_worst(by_lander)
    conclusions["lander_id"] = {
        "metrics": {"count": len(by_lander)},
        "conclusion": _format_conclusion("lander", best_lander, worst_lander, name_key="lander_id") if by_lander else "Нет разбивки по Lander.",
    }

    # 7. Traffic Source
    conclusions["traffic_source"] = {
        "metrics": {},
        "conclusion": "Источник трафика. Используется для фильтрации кампаний.",
    }

    # 8. Device Type
    by_device = breakdown.get("by_device_type") or []
    best_dev, worst_dev = _best_worst(by_device)
    conclusions["device_type"] = {
        "metrics": {"count": len(by_device)},
        "conclusion": _format_conclusion("device", best_dev, worst_dev, name_key="device_type") if by_device else "Нет разбивки по Device.",
    }

    # 9. Country
    by_country = breakdown.get("by_country") or []
    best_c, worst_c = _best_worst(by_country)
    conclusions["country"] = {
        "metrics": {"count": len(by_country)},
        "conclusion": _format_conclusion("country", best_c, worst_c) if by_country else "Нет разбивки по Country.",
    }

    # 10. OS
    by_os = breakdown.get("by_os") or []
    best_os, worst_os = _best_worst(by_os)
    conclusions["os"] = {
        "metrics": {"count": len(by_os)},
        "conclusion": _format_conclusion("os", best_os, worst_os, name_key="os") if by_os else "Нет разбивки по OS.",
    }

    # 11–12. OS Version, Browser Name — обычно нет в breakdown
    conclusions["os_version"] = {"metrics": {}, "conclusion": "Нет детальной разбивки в отчёте."}
    conclusions["browser_name"] = {"metrics": {}, "conclusion": "Нет детальной разбивки в отчёте."}

    # 13. Language
    conclusions["language"] = {"metrics": {}, "conclusion": "Нет детальной разбивки в отчёте."}

    # 14. Payout (revenue)
    conclusions["payout"] = {
        "metrics": {"revenue": revenue},
        "conclusion": f"Payout ${revenue}. {'Низкий при таком spend.' if spend > 0 and revenue / spend < 0.5 else 'В норме.'}",
    }

    # 15. Conversion
    conclusions["conversion"] = {
        "metrics": {"conversions": conversions, "cr_pct": cr_pct},
        "conclusion": f"{conversions} конверсий, CR {cr_pct}%. {'Мало конверсий для выводов.' if conversions < 3 else 'Достаточно данных.'}",
    }

    # 16. Cost
    conclusions["cost"] = {
        "metrics": {"spend": spend},
        "conclusion": f"Spend ${spend}. {'Достаточно для анализа.' if spend >= 20 else 'Мало данных (min $20).'}",
    }

    # 17–26. Tokens 1–10
    by_token2 = breakdown.get("by_token2") or []
    best_t2, worst_t2 = _best_worst(by_token2)
    conclusions["token1"] = {"metrics": {}, "conclusion": "Token1 = Campaign ID. Без отдельного анализа."}
    conclusions["token2"] = {
        "metrics": {"count": len(by_token2)},
        "conclusion": _format_conclusion("token2", best_t2, worst_t2) if by_token2 else "Нет разбивки по creative.",
    }
    for i in range(3, 11):
        conclusions[f"token{i}"] = {"metrics": {}, "conclusion": "Нет разбивки в отчёте."}

    return conclusions
