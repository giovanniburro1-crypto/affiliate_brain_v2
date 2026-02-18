"""
trend_analysis - мигрированный блок из JSON.
"""

from typing import Dict, List, Optional, Any
from backend.brain.knowledge_base_v2_complete import KnowledgeBlock
import json


class TrendAnalysisBlock(KnowledgeBlock):
    """Блок знаний из trend_analysis.json"""
    
    def __init__(self):
        super().__init__(
            name="trend_analysis",
            description="Блок знаний из trend_analysis.json",
            weight=1.0,
            category="patterns"
        )
        self.json_data = json.loads("""{
  "weekly_trends": {},
  "monthly_seasonality": {},
  "hourly_patterns": {
    "peak_hours": [],
    "worst_hours": [],
    "best_cpc": []
  }
}""")
    
    def analyze(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        roi = campaign_data.get("roi", 0)
        profit = campaign_data.get("profit", 0)
        spend = campaign_data.get("spend", 0)
        clicks = campaign_data.get("clicks", 0)
        conversions = campaign_data.get("conversions", 0)
        volatility = campaign_data.get("volatility", 0)
        
        verdict = "HOLD"
        confidence = 50.0
        reasoning = []
        
        try:
            # Простая логика на основе JSON данных
            if "killer_rules" in self.json_data:
                killer = self.json_data["killer_rules"]
                if roi < killer.get("roi_threshold", -20):
                    verdict = "STOP"
                    confidence = 80.0
                    reasoning.append(f"ROI ниже порога")
            
            if "scaler_rules" in self.json_data:
                scaler = self.json_data["scaler_rules"]
                if roi > scaler.get("min_roi", 30) and conversions >= scaler.get("min_conversions", 3):
                    verdict = "SCALE"
                    confidence = 75.0
                    reasoning.append(f"Хороший ROI и конверсии")
            
            if "optimizer_rules" in self.json_data:
                optimizer = self.json_data["optimizer_rules"]
                epc = profit / clicks if clicks > 0 else 0
                if epc < optimizer.get("epc_threshold", 0.15):
                    verdict = "OPTIMIZE"
                    confidence = 70.0
                    reasoning.append(f"Низкий EPC")
            
            # Общая логика
            if not reasoning:
                if roi > 20:
                    verdict = "SCALE"
                    confidence = 60.0
                elif roi < -10:
                    verdict = "STOP"
                    confidence = 55.0
                elif -5 <= roi <= 15:
                    verdict = "HOLD"
                    confidence = 50.0
                else:
                    verdict = "OPTIMIZE"
                    confidence = 45.0
                    
        except Exception as e:
            verdict = "HOLD"
            confidence = 30.0
            reasoning.append(f"Ошибка: {str(e)}")
        
        return {
            "verdict": verdict,
            "confidence": min(100.0, max(0.0, confidence)),
            "reasoning": reasoning,
            "block_name": self.name
        }
    
    def get_config_summary(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "weight": self.weight,
            "category": self.category,
            "source_file": "trend_analysis.json"
        }


def register_block():
    return TrendAnalysisBlock()
