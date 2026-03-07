"""
ACTION PLAN — ответ сеньора аффилейт-менеджера.
Глубокий анализ: Key Drivers (killers/strengths) + path/offer/lander + my_knowledge.
Формат: что делать с кампанией, приоритизировано, с обоснованием.
"""
import sys
import os

_my_knowledge_path = os.path.join(os.path.dirname(__file__), '../../logic_blocks/my_knowledge')
if _my_knowledge_path not in sys.path:
    sys.path.insert(0, _my_knowledge_path)

_blocks = {}
for mod, cls in [
    ("block_1_base", "AffiliateKnowledgeBase"),
    ("block_5_scale", "AffiliateExperimentsPhase5"),
    ("block_6_payouts", "AffiliatePayoutEnginePhase6"),
    ("block_3_crisis", "AffiliateBlacklistEngine"),
]:
    try:
        m = __import__(mod.replace("-", "_"), fromlist=[cls])
        _blocks[cls] = getattr(m, cls)
    except (ImportError, AttributeError):
        pass

BLOCKS_LOADED = "AffiliateKnowledgeBase" in _blocks


def _fmt(v):
    return f"${float(v):.0f}" if v is not None else "—"


class ActionPlanGenerator:
    """Генератор — что делать с кампанией. Формат сеньора: контекст + план по приоритету."""

    def __init__(self):
        self.block1 = _blocks.get("AffiliateKnowledgeBase") and _blocks["AffiliateKnowledgeBase"]()
        self.block3 = _blocks.get("AffiliateBlacklistEngine") and _blocks["AffiliateBlacklistEngine"]()
        self.block5 = _blocks.get("AffiliateExperimentsPhase5") and _blocks["AffiliateExperimentsPhase5"]()
        self.block6 = _blocks.get("AffiliatePayoutEnginePhase6") and _blocks["AffiliatePayoutEnginePhase6"]()

    def generate_actions(self, analysis, breakdown, path_offer_lander):
        if not BLOCKS_LOADED:
            return [{"type": "error", "text": "my_knowledge не загружен", "reason": "Проверь logic_blocks/my_knowledge/"}]

        spend = float(analysis.get("spend", 0) or 0)
        revenue = float(analysis.get("revenue", 0) or 0)
        profit = float(analysis.get("profit", 0) or 0)
        conversions = int(analysis.get("conversions", 0) or 0)
        roi = float(analysis.get("roi", 0) or 0)
        volatility = float(analysis.get("volatility", 0) or 0)
        verdict = (analysis.get("verdict") or "HOLD").upper()
        killers = analysis.get("profit_killers") or []
        strengths = analysis.get("strengths") or []
        weaknesses = analysis.get("weaknesses") or []
        path_offer_lander = path_offer_lander or []
        avg_payout = revenue / conversions if conversions > 0 else 10.0

        actions = []

        # === BLOCK 1 & 6: Критические стопы ===
        stop = self.block1.analyze_stop_loss(spend, avg_payout, conversions)
        if stop.get("action") == "STOP IMMEDIATELY":
            return [{"type": "kill", "text": "STOP CAMPAIGN", "reason": stop["reason"]}]
        if self.block6:
            bl = self.block6.calculate_blacklist_threshold_by_payout(avg_payout, spend, roi / 100 if roi else 0)
            if bl.get("action") in ["BLACKLIST IMMEDIATE", "BLACKLIST (Hard Stop)"]:
                return [{"type": "kill", "text": "BLACKLIST", "reason": bl["reason"]}]

        # === КОНТЕКСТ: почему вердикт, что с кампанией ===
        ctx = self._build_context(profit, roi, volatility, verdict, conversions, spend)
        if ctx:
            actions.append({"type": "insight", "text": ctx["headline"], "reason": ctx["reason"]})

        # === 1. KILLERS — одним блоком, с эффектом ===
        if killers:
            total_kill_spend = sum(k.get("spend", 0) or 0 for k in killers)
            names = ", ".join(f"{k.get('type', '')} {k.get('value', '')}" for k in killers[:5])
            actions.append({
                "type": "kill",
                "text": f"Выключить: {names}",
                "reason": f"0 конверсий, слив {_fmt(total_kill_spend)} (правило 2×payout). Прирост профита ~{_fmt(total_kill_spend)}.",
            })

        # === 2. ТОП-СИЛА — конкретный совет (Whitelist / изоляция) ===
        if strengths and self.block1:
            top = max(strengths, key=lambda s: float(s.get("profit", 0) or 0))
            tp = float(top.get("profit", 0) or 0)
            ts = float(top.get("spend", 0) or 0)
            tc = int(top.get("conversions", 0) or 0)
            label = f"{top.get('type', '')} {top.get('value', '')}"
            zacep = self.block1.find_zacep(tc)
            if tc >= 3 and tp > 20:
                if zacep.get("status") == "ZACEP FOUND!":
                    whitelist = self.block1.scaling_strategy_whitelist(0.5, ts / (tc or 1) if tc else 0, False)
                    actions.append({
                        "type": "isolate",
                        "text": f"Зацеп: {label} — рассмотри Whitelist (+20% к биду)",
                        "reason": f"{tc} конв, +{_fmt(tp)}. {whitelist.get('logic', '')}",
                    })
                else:
                    actions.append({
                        "type": "isolate",
                        "text": f"Лидер: {label} — вынести в отдельный path",
                        "reason": f"{tc} конв, +{_fmt(tp)}, {_fmt(ts)} spend. Убрать конкурентов из ротации.",
                    })

        # === 3. PATH → OFFER → LANDER: минусовые связки ===
        losers = [c for c in path_offer_lander if float(c.get("profit", 0) or 0) < -15]
        if losers:
            for c in losers[:2]:
                path_lander = f"{c.get('path', '')}/{c.get('lander_id', '')}"
                if (c.get("path") and c.get("path") != "(empty)") or (c.get("lander_id") and c.get("lander_id") != "(empty)"):
                    actions.append({
                        "type": "optimize",
                        "text": f"Path/Lander {path_lander}: отключить или снизить бид",
                        "reason": f"Profit {_fmt(c.get('profit'))}. Слив без перспективы.",
                    })

        # === 4. SCALE — только при устойчивом плюсе (block5) ===
        if self.block5 and profit > 0 and roi > 25 and conversions >= 3 and volatility < 25:
            sc = self.block5.calculate_aggressive_budget_increase(max(50, spend * 0.1), True)
            if sc.get("action") == "SCALE IMMEDIATELY":
                actions.append({
                    "type": "scale",
                    "text": "SCALE: поднять бюджет на 30–50%",
                    "reason": sc.get("recommendation", "") + " " + (sc.get("logic", "") or ""),
                })

        # === 5. Кросс-сегментация: не дублировать изоляцию ===
        if len(strengths) >= 3 and len([a for a in actions if a.get("type") == "isolate"]) > 1:
            # Много плюсовых сегментов — вероятно один трафик с разных сторон
            actions.append({
                "type": "insight",
                "text": "Много сегментов в плюсе — возможна кросс-сегментация (один трафик). Фокус на killers и топ-1 лидере.",
                "reason": "Не дублируй изоляцию по TOKEN3/4/5, OS, Device — это может быть один креатив.",
            })

        # Убираем дубли insight, оставляем max 2
        insights = [a for a in actions if a.get("type") == "insight"]
        others = [a for a in actions if a.get("type") != "insight"]
        insights = insights[:2]
        actions = insights + others
        return actions[:7]  # макс 7 пунктов

    def _build_context(self, profit, roi, volatility, verdict, conversions, spend):
        """Короткий контекст: что с кампанией, почему вердикт."""
        p = _fmt(profit)
        if profit >= 0:
            if verdict == "STOP":
                return {"headline": f"Кампания в плюсе {p}, но STOP.", "reason": "Возможно слив по тренду или 3+ дней минуса подряд."}
            if verdict == "HOLD":
                if volatility > 30:
                    return {"headline": f"Profit {p}, ROI {roi}%. Вердикт HOLD.", "reason": f"Волатильность {volatility:.0f}% — сначала стабилизируй (killers, path), потом скейл."}
                return {"headline": f"Profit {p}, ROI {roi}%. HOLD.", "reason": "Чисти killers, фиксируй зацеп, затем скейл."}
            if verdict == "SCALE":
                return {"headline": f"Profit {p}, ROI {roi}%. Готов к SCALE.", "reason": "Стабильный плюс. Выключи killers → поднимай бюджет."}
            if verdict == "OPTIMIZE":
                return {"headline": f"Profit {p}, ROI {roi}%. OPTIMIZE.", "reason": "Есть потенциал. Убери сливы, усиль лидера."}
        else:
            return {"headline": f"Кампания в минусе {p}.", "reason": "Сначала killers и path. При 0 конв и spend > 2×payout — стоп."}
        return None
