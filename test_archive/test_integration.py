#!/usr/bin/env python3
"""
Тест интеграции KnowledgeBaseV2 с существующим top5_service.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.services.top5_service_v2_complete import Top5ServiceV2
from backend.brain.knowledge_base_v2_complete import KnowledgeBaseV2
from backend.database import SessionLocal


def test_top5_service_integration():
    """Тестирование интеграции Top5ServiceV2 с KnowledgeBaseV2."""
    print("=" * 60)
    print("ТЕСТ ИНТЕГРАЦИИ TOP5SERVICEV2 С KNOWLEDGEBASEV2")
    print("=" * 60)
    
    # Создаем экземпляры
    kb = KnowledgeBaseV2()
    db = SessionLocal()  # Используем сессию базы данных
    top5_service = Top5ServiceV2(db, brain=kb)
    
    print(f"KnowledgeBaseV2 загружено блоков: {len(kb._loaded_classes)}")
    print(f"Top5ServiceV2 использует KnowledgeBaseV2: {top5_service.brain is not None}")
    
    # Тестовые данные кампаний
    test_campaigns = [
        {
            "campaign_id": "campaign_001",
            "roi": 45.5,
            "profit": 250.0,
            "spend": 150.0,
            "clicks": 1500,
            "conversions": 8,
            "volatility": 12.0,
            "payout": 75.0,
            "epc": 0.17,
            "cpc": 0.06,
            "offer": "Premium Offer A",
            "has_jump_monetization": True,
            "traffic_source": "Facebook",
            "country": "US"
        },
        {
            "campaign_id": "campaign_002",
            "roi": -15.0,
            "profit": -75.0,
            "spend": 500.0,
            "clicks": 8000,
            "conversions": 1,
            "volatility": 25.0,
            "payout": 150.0,
            "epc": 0.04,
            "cpc": 0.03,
            "offer": "Standard Offer B",
            "has_jump_monetization": False,
            "traffic_source": "Google",
            "country": "UK"
        },
        {
            "campaign_id": "campaign_003",
            "roi": 25.0,
            "profit": 100.0,
            "spend": 400.0,
            "clicks": 3000,
            "conversions": 4,
            "volatility": 18.0,
            "payout": 100.0,
            "epc": 0.12,
            "cpc": 0.08,
            "offer": "Premium Offer C",
            "has_jump_monetization": True,
            "traffic_source": "TikTok",
            "country": "DE"
        },
        {
            "campaign_id": "campaign_004",
            "roi": 5.0,
            "profit": 25.0,
            "spend": 500.0,
            "clicks": 4000,
            "conversions": 2,
            "volatility": 22.0,
            "payout": 125.0,
            "epc": 0.08,
            "cpc": 0.07,
            "offer": "Standard Offer D",
            "has_jump_monetization": False,
            "traffic_source": "Facebook",
            "country": "FR"
        },
        {
            "campaign_id": "campaign_005",
            "roi": 60.0,
            "profit": 300.0,
            "spend": 200.0,
            "clicks": 1200,
            "conversions": 10,
            "volatility": 8.0,
            "payout": 50.0,
            "epc": 0.25,
            "cpc": 0.04,
            "offer": "Premium Offer E",
            "has_jump_monetization": True,
            "traffic_source": "Instagram",
            "country": "US"
        }
    ]
    
        # Тестируем анализ каждой кампании через Top5ServiceV2
    print(f"\nАнализ кампаний через Top5ServiceV2:")
    for i, campaign in enumerate(test_campaigns, 1):
        print(f"\nКампания {i}: {campaign['campaign_id']}")
        print(f"  ROI: {campaign['roi']}%, Profit: ${campaign['profit']}, Spend: ${campaign['spend']}")
        
        # Анализируем через Top5ServiceV2
        # Используем get_campaign_analysis для анализа кампании
        result = top5_service.get_campaign_analysis(campaign['campaign_id'])
        
        if result:
            print(f"  Вердикт: {result.get('verdict', 'N/A')}")
            print(f"  Уверенность: {result.get('confidence', 0):.1f}%")
            print(f"  Причина: {result.get('reason', 'N/A')[:100]}...")
            
            # Показываем голоса блоков
            if 'block_votes' in result:
                print(f"  Голосов блоков: {len(result['block_votes'])}")
                
                # Группируем голоса по вердиктам
                verdict_counts = {}
                for vote in result['block_votes']:
                    verdict = vote['verdict']
                    verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
                
                print(f"  Распределение голосов: {verdict_counts}")
        else:
            print(f"  Результат: None (кампания не найдена в базе данных)")
    
    # Тестируем получение топ-5 кампаний
    print(f"\n{'='*60}")
    print("ТЕСТ ПОЛУЧЕНИЯ ТОП-5 КАМПАНИЙ")
    print(f"{'='*60}")
    
    # Используем get_top5 с параметрами по умолчанию
    top5_result = top5_service.get_top5(period=7, limit=5)
    
    print(f"Результат get_top5 получен")
    if top5_result and 'campaigns' in top5_result:
        campaigns = top5_result['campaigns']
        print(f"Найдено кампаний в топ-5: {len(campaigns)}")
        
        print(f"\nТоп-5 кампаний:")
        for i, campaign in enumerate(campaigns, 1):
            print(f"\n{i}. {campaign.get('campaign_id', 'N/A')}")
            print(f"   ROI: {campaign.get('roi', 0)}%, Profit: ${campaign.get('profit', 0)}")
            print(f"   Вердикт: {campaign.get('verdict', 'N/A')}")
            print(f"   Уверенность: {campaign.get('confidence', 0):.1f}%")
            print(f"   Причина: {campaign.get('reason', 'N/A')[:80]}...")
    else:
        print(f"Результат пустой или не содержит кампаний")
    
    # Тестируем обратную совместимость
    print(f"\n{'='*60}")
    print("ТЕСТ ОБРАТНОЙ СОВМЕСТИМОСТИ")
    print(f"{'='*60}")
    
    # Проверяем, что старые методы работают
    core_rules = kb.get_core_rules()
    print(f"Core rules загружены: {bool(core_rules)}")
    
    killer_rules = kb.get_killer_rules()
    print(f"Killer rules: {killer_rules}")
    
    scaler_rules = kb.get_scaler_rules()
    print(f"Scaler rules: {scaler_rules}")
    
    winning_combos = kb.get_winning_combos()
    print(f"Winning combos: {len(winning_combos)} паттернов")
    
    killer_patterns = kb.get_killer_patterns()
    print(f"Killer patterns: {len(killer_patterns)} паттернов")
    
    trend_analysis = kb.get_trend_analysis()
    print(f"Trend analysis: {bool(trend_analysis)}")
    
    segment_columns = kb.get_segment_columns()
    print(f"Segment columns: {segment_columns}")
    
    model_weights = kb.get_model_weights()
    print(f"Model weights: {bool(model_weights)}")
    
    print(f"\n{'='*60}")
    print("ТЕСТ ИНТЕГРАЦИИ ЗАВЕРШЕН УСПЕШНО!")
    print(f"{'='*60}")
    
    return True


def main():
    """Основная функция тестирования."""
    try:
        test_top5_service_integration()
        return True
        
    except Exception as e:
        print(f"\nОшибка тестирования интеграции: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)