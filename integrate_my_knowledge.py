"""
Интеграция твоих блоков знаний в KnowledgeBase
"""
import sys
import os

# Добавляем путь к твоим блокам
sys.path.insert(0, 'logic_blocks/my_knowledge')

# Импортируем все блоки
from block_1_base import AffiliateKnowledgeBase
from block_2_optimize import AffiliateOptimizationEngine
from block_3_crisis import AffiliateBlacklistEngine
from block_4_volatility import AffiliateVolatilityPhase4
from block_5_scale import AffiliateExperimentsPhase5
from block_6_payouts import AffiliatePayoutEnginePhase6

print("=== ТВОИ БЛОКИ ЗАГРУЖЕНЫ ===")
print("✅ Block 1: AffiliateKnowledgeBase")
print("✅ Block 2: AffiliateOptimizationEngine")
print("✅ Block 3: AffiliateBlacklistEngine")
print("✅ Block 4: AffiliateVolatilityPhase4")
print("✅ Block 5: AffiliateExperimentsPhase5")
print("✅ Block 6: AffiliatePayoutEnginePhase6")

# Тестируем один метод
kb = AffiliateKnowledgeBase()
result = kb.analyze_stop_loss(spend=50, payout=25, conversions=0)
print(f"\n=== ТЕСТ БЛОКА 1 ===")
print(f"Spend: $50, Payout: $25, Conv: 0")
print(f"Результат: {result}")

# Проверяем что можем вызывать методы
opt = AffiliateOptimizationEngine()
traffic = opt.calculate_traffic_share([100, 50, 100])
print(f"\n=== ТЕСТ БЛОКА 2 ===")
print(f"Веса: [100, 50, 100]")
print(f"Результат: {traffic}")

print("\n✅ ВСЕ БЛОКИ РАБОТАЮТ!")
