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
    """Форматирует короткий вывод: что работает, что нет. Показываем топ и худший даже при profit=0."""
    parts = []
    if best:
        name = best.get(name_key, best.get("offer_id", best.get("lander_id", "—")))
        prof = best.get("profit", 0)
        parts.append(f"Топ: {name} (profit ${prof})")
    if worst and worst != best:
        name = worst.get(name_key, worst.get("offer_id", worst.get("lander_id", "—")))
        prof = worst.get("profit", 0)
        parts.append(f"Худший: {name} (profit ${prof})")
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

    # 11–12. OS Version, Browser Name
    by_os_version = breakdown.get("by_os_version") or []
    best_ov, worst_ov = _best_worst(by_os_version)
    conclusions["os_version"] = {
        "metrics": {"count": len(by_os_version)},
        "conclusion": _format_conclusion("os_version", best_ov, worst_ov, name_key="os_version") if by_os_version else "Нет разбивки по OS Version.",
    }
    by_browser = breakdown.get("by_browser_name") or []
    best_br, worst_br = _best_worst(by_browser)
    conclusions["browser_name"] = {
        "metrics": {"count": len(by_browser)},
        "conclusion": _format_conclusion("browser", best_br, worst_br, name_key="browser_name") if by_browser else "Нет разбивки по Browser.",
    }

    # 13. Language
    by_language = breakdown.get("by_language") or []
    best_lang, worst_lang = _best_worst(by_language)
    conclusions["language"] = {
        "metrics": {"count": len(by_language)},
        "conclusion": _format_conclusion("language", best_lang, worst_lang, name_key="language") if by_language else "Нет разбивки по Language.",
    }

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
        "conclusion": _format_conclusion("token2", best_t2, worst_t2, name_key="name") if by_token2 else "Нет разбивки по creative.",
    }
    for i in range(3, 11):
        by_t = breakdown.get(f"by_token{i}") or []
        best_t, worst_t = _best_worst(by_t)
        conclusions[f"token{i}"] = {
            "metrics": {"count": len(by_t)},
            "conclusion": _format_conclusion(f"token{i}", best_t, worst_t, name_key=f"token{i}") if by_t else f"Нет разбивки по Token {i}.",
        }

    return conclusions


def get_bot_actions(
    analysis: Dict[str, Any],
    path_offer_lander: List[Dict[str, Any]],
    breakdown: Dict[str, Any],
    brain: Optional[KnowledgeBase] = None,
) -> List[Dict[str, Any]]:
    """
    Генерирует рекомендации бота (Logic Blocks): kill, isolate, optimize.
    Порядок: kill → isolate → optimize.
    """
    brain = brain or KnowledgeBase()
    zacep_rules = brain.get_zacep_rules()
    min_conv_zacep = zacep_rules.get("min_conversions", 3)
    roi_isolate_threshold = 15

    actions: List[Dict[str, Any]] = []
    killers = analysis.get("profit_killers") or []
    strengths = analysis.get("strengths") or []
    conversions = analysis.get("conversions") or 0

    has_zacep = any(
        s.get("conversions", 0) >= min_conv_zacep and (s.get("profit") or 0) > 0
        for s in strengths
    ) or conversions >= min_conv_zacep

    for k in killers:
        actions.append({
            "type": "kill",
            "param": k.get("type"),
            "value": str(k.get("value", "")),
            "text": f"Отключить {k.get('type', '')} {k.get('value', '')}",
            "reason": f"0 conv, spend ${k.get('spend', 0)} > 2× payout",
        })

    if has_zacep and path_offer_lander:
        for c in path_offer_lander:
            roi = c.get("roi") or 0
            profit = c.get("profit") or 0
            if 0 < roi < roi_isolate_threshold and profit > 0:
                actions.append({
                    "type": "isolate",
                    "path": c.get("path"),
                    "offer_id": c.get("offer_id"),
                    "lander_id": c.get("lander_id"),
                    "text": f"Вынести Offer {c.get('offer_id', '')} / Lander {c.get('lander_id', '')} в отдельный path",
                    "reason": f"ROI {roi}% при слабом трафике — изолировать по zacep",
                })
                break

    for c in path_offer_lander:
        profit = c.get("profit") or 0
        if profit < 0:
            actions.append({
                "type": "optimize",
                "path": c.get("path"),
                "lander_id": c.get("lander_id"),
                "text": f"Path {c.get('path', '')} + Lander {c.get('lander_id', '')}: отключить или снизить бид",
                "reason": f"Profit ${profit}, стабильный минус",
            })

    return actions
