"""
ACTION PLAN Generator - анализирует ВСЕ параметры универсально
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../logic_blocks/my_knowledge'))
from backend.brain import KnowledgeBase

try:
    from block_1_base import AffiliateKnowledgeBase
    from block_6_payouts import AffiliatePayoutEnginePhase6
    from block_5_scale import AffiliateExperimentsPhase5
    BLOCKS_LOADED = True
except:
    BLOCKS_LOADED = False

class ActionPlanGenerator:
    def __init__(self):
        if BLOCKS_LOADED:
            self.block1 = AffiliateKnowledgeBase()
            self.block5 = AffiliateExperimentsPhase5()
            self.block6 = AffiliatePayoutEnginePhase6()
    
    def generate_actions(self, analysis, breakdown, path_offer_lander):
        if not BLOCKS_LOADED:
            return [{"type": "error", "text": "Blocks not loaded"}]
        
        actions = []
        spend = float(analysis.get("spend", 0) or 0)
        revenue = float(analysis.get("revenue", 0) or 0)
        profit = float(analysis.get("profit", 0) or 0)
        conversions = int(analysis.get("conversions", 0) or 0)
        roi = float(analysis.get("roi", 0) or 0)
        
        avg_payout = revenue / conversions if conversions > 0 else 10.0
        
        # BLOCK 1: Stop Loss
        stop = self.block1.analyze_stop_loss(spend, avg_payout, conversions)
        if stop.get("action") == "STOP IMMEDIATELY":
            return [{"type": "kill", "text": "STOP CAMPAIGN", "reason": stop["reason"], "confidence": "CRITICAL"}]
        
        # BLOCK 6: Blacklist
        bl = self.block6.calculate_blacklist_threshold_by_payout(avg_payout, spend, roi/100 if roi else 0)
        if bl.get("action") in ["BLACKLIST IMMEDIATE", "BLACKLIST (Hard Stop)"]:
            actions.append({"type": "kill", "text": "BLACKLIST", "reason": bl["reason"], "confidence": "HIGH"})
        
        # BLOCK 5: Scale
        if profit > 0 and roi > 30 and conversions >= 3:
            sc = self.block5.calculate_aggressive_budget_increase(50, True)
            if sc.get("action") == "SCALE IMMEDIATELY":
                actions.append({"type": "scale", "text": "SCALE +30-50%", "reason": sc["recommendation"], "confidence": "HIGH"})
        
        # Analyze all tokens and params
        for i in range(2, 11):
            self._analyze_param(breakdown, f"by_token{i}", f"TOKEN{i}", f"token{i}", avg_payout, spend, actions)
        
        self._analyze_param(breakdown, "by_offer_id", "OFFER", "offer_id", avg_payout, spend, actions)
        self._analyze_param(breakdown, "by_lander_id_jump", "LANDER", "lander_id", avg_payout, spend, actions)
        self._analyze_param(breakdown, "by_os", "OS", "os", avg_payout, spend, actions)
        
        return sorted(actions, key=lambda x: {"kill":1,"scale":2,"isolate":3}.get(x["type"], 9))
    
    def _analyze_param(self, breakdown, param_key, label, value_key, avg_payout, total_spend, actions):
        items = breakdown.get(param_key, [])
        if not items or len(items) <= 1:
            return
        
        items = [x for x in items if x.get(value_key) not in [None, "(empty)", ""]]
        if not items or len(items) <= 1:
            return
        
        sorted_items = sorted(items, key=lambda x: float(x.get("profit", 0) or 0), reverse=True)
        best, worst = sorted_items[0], sorted_items[-1]
        
        bp = float(best.get("profit", 0) or 0)
        bc = int(best.get("conversions", 0) or 0)
        bs = float(best.get("spend", 0) or 0)
        
        wp = float(worst.get("profit", 0) or 0)
        ws = float(worst.get("spend", 0) or 0)
        wc = int(worst.get("conversions", 0) or 0)
        
        bv = str(best.get(value_key))
        wv = str(worst.get(value_key))
        
        # Killer: x1 payout rule OR >20% budget killed
        payout_mult = ws / avg_payout if avg_payout > 0 else 0
        budget_pct = (ws / total_spend * 100) if total_spend > 0 else 0
        
        if (wc == 0 and payout_mult >= 1.0) or (wp < -10 and budget_pct > 20):
            actions.append({
                "type": "kill",
                "text": f"STOP {label}: {wv}",
                "reason": f"${ws:.0f} spent ({budget_pct:.0f}% budget), profit ${wp:.0f}, {wc} conv",
                "confidence": "HIGH"
            })
        
        # Winner: 3+ conv and profit > $5
        if bc >= 3 and bp > 5:
            actions.append({
                "type": "isolate",
                "text": f"ISOLATE {label}: {bv}",
                "reason": f"{bc} conv, +${bp:.0f}, ${bs:.0f} spent",
                "confidence": "HIGH"
            })
