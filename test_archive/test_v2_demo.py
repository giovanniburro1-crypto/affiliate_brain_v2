#!/usr/bin/env python3
"""
Демонстрация работы системы V2 с динамическими блоками.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.brain.knowledge_base_v2_complete import KnowledgeBaseV2
from backend.services.top5_service_v2_complete import Top5ServiceV2
from backend.database import SessionLocal


def demo_knowledge_base_v2():
    """Демонстрация работы KnowledgeBaseV2."""
    print("=" * 60)
    print("ДЕМОНСТРАЦИЯ KNOWLEDGEBASEV2")
    print("=" * 60)
    
    # Создаем экземпляр KnowledgeBaseV2
    kb = KnowledgeBaseV2()
    
    print(f"Загружено блоков: {len(kb._loaded_classes)}")
    
    # Показываем загруженные блоки
    print(f"\nЗагруженные блоки из my_knowledge:")
    for block_name, block_class in kb._loaded_classes.items():
        print(f"  - {block_name}: {block_class.__name__}")
    
    # Проверяем наличие мигрированных блоков
    print(f"\nЗагруженные мигрированные блоки:")
    migrated_count = 0
    if hasattr(kb, '_migrated_blocks_dict'):
        migrated_count = len(kb._migrated_blocks_dict)
        for block_name in kb._migrated_blocks_dict.keys():
            print(f"  - {block_name}")
    print(f"Всего мигрированных блоков: {migrated_count}")
    
    # Демонстрация анализа кампании
    print(f"\nДЕМОНСТРАЦИЯ АНАЛИЗА КАМПАНИИ:")
    
    test_campaign = {
        "campaign_id": "test_campaign_001",
        "roi": 45.5,
        "profit": 250.0,
        "spend": 150.0,
        "clicks": 1500,
        "conversions": 8,
        "volatility": 12.0,
        "daily_impact": [50, 60, 45, 70, 55, 65, 50]
    }
    
    print(f"Тестовая кампания:")
    print(f"  ROI: {test_campaign['roi']}%")
    print(f"  Profit: ${test_campaign['profit']}")
    print(f"  Spend: ${test_campaign['spend']}")
    print(f"  Clicks: {test_campaign['clicks']}")
    print(f"  Conversions: {test_campaign['conversions']}")
    print(f"  Volatility: {test_campaign['volatility']}%")
    
    # Анализируем кампанию
    result = kb.analyze_campaign_simple(test_campaign)
    
    if result:
        print(f"\nРезультат анализа:")
        print(f"  Финальный вердикт: {result.get('final_verdict', 'N/A')}")
        print(f"  Уверенность: {result.get('confidence', 0):.1f}%")
        
        if 'block_votes' in result:
            print(f"\n  Голоса блоков:")
            for vote in result['block_votes']:
                block_name = vote.get('block_name', 'Unknown')
                verdict = vote.get('verdict', 'N/A')
                confidence = vote.get('confidence', 0)
                reasoning = vote.get('reasoning', '')[:80]
                print(f"    - {block_name}: {verdict} (уверенность: {confidence:.1f}%)")
                print(f"      Причина: {reasoning}...")
        
        # Также показываем голосование через vote_on_campaign
        print(f"\n  Детальное голосование через vote_on_campaign:")
        votes = kb.vote_on_campaign(test_campaign)
        if votes:
            for block_name, vote_info in votes.items():
                if isinstance(vote_info, dict):
                    verdict = vote_info.get('verdict', 'N/A')
                    confidence = vote_info.get('confidence', 0)
                    print(f"    - {block_name}: {verdict} (уверенность: {confidence:.1f}%)")
    
    # Демонстрация обратной совместимости
    print(f"\nДЕМОНСТРАЦИЯ ОБРАТНОЙ СОВМЕСТИМОСТИ:")
    
    core_rules = kb.get_core_rules()
    print(f"  Core rules: {bool(core_rules)}")
    
    killer_rules = kb.get_killer_rules()
    print(f"  Killer rules: {killer_rules}")
    
    scaler_rules = kb.get_scaler_rules()
    print(f"  Scaler rules: {scaler_rules}")
    
    winning_combos = kb.get_winning_combos()
    print(f"  Winning combos: {len(winning_combos)} паттернов")
    
    killer_patterns = kb.get_killer_patterns()
    print(f"  Killer patterns: {len(killer_patterns)} паттернов")
    
    trend_analysis = kb.get_trend_analysis()
    print(f"  Trend analysis: {bool(trend_analysis)}")
    
    segment_columns = kb.get_segment_columns()
    print(f"  Segment columns: {segment_columns}")
    
    model_weights = kb.get_model_weights()
    print(f"  Model weights: {bool(model_weights)}")
    
    return kb


def demo_top5_service_v2():
    """Демонстрация работы Top5ServiceV2."""
    print(f"\n{'='*60}")
    print("ДЕМОНСТРАЦИЯ TOP5SERVICEV2")
    print(f"{'='*60}")
    
    # Создаем экземпляры
    kb = KnowledgeBaseV2()
    db = SessionLocal()
    top5_service = Top5ServiceV2(db, brain=kb)
    
    print(f"Top5ServiceV2 использует KnowledgeBaseV2: {top5_service.brain is not None}")
    
    # Демонстрация методов
    print(f"\nДоступные методы Top5ServiceV2:")
    methods = [m for m in dir(top5_service) if not m.startswith('_')]
    for method in methods:
        print(f"  - {method}")
    
    # Демонстрация работы с тестовыми данными
    print(f"\nДЕМОНСТРАЦИЯ РАБОТЫ С ТЕСТОВЫМИ ДАННЫМИ:")
    
    # Создаем тестовые данные в базе данных
    print(f"  (В реальной системе здесь были бы данные из базы данных)")
    
    # Показываем структуру результата
    print(f"\n  Структура результата get_top5():")
    print(f"    - campaigns: список топ-5 кампаний")
    print(f"    - all_campaigns: все проанализированные кампании")
    print(f"    - summary: сводная статистика")
    
    print(f"\n  Структура результата get_campaign_analysis():")
    print(f"    - campaign_id: ID кампании")
    print(f"    - verdict: вердикт (SCALE/STOP/OPTIMIZE/HOLD)")
    print(f"    - confidence: уверенность в %")
    print(f"    - block_votes: голоса блоков")
    print(f"    - strengths: сильные сегменты")
    print(f"    - weaknesses: слабые сегменты")
    
    return top5_service


def demo_learning_system():
    """Демонстрация системы обучения."""
    print(f"\n{'='*60}")
    print("ДЕМОНСТРАЦИЯ СИСТЕМЫ ОБУЧЕНИЯ")
    print(f"{'='*60}")
    
    kb = KnowledgeBaseV2()
    
    # Демонстрация обучения на основе решений пользователя
    print(f"Система обучения позволяет:")
    print(f"  1. Записывать решения пользователя")
    print(f"  2. Анализировать корреляцию с голосами блоков")
    print(f"  3. Настраивать веса блоков")
    print(f"  4. Улучшать точность рекомендаций")
    
    # Пример обучения
    print(f"\nПример обучения:")
    
    # Создаем тестовое решение пользователя
    user_decision = {
        "campaign_id": "test_campaign_001",
        "user_verdict": "SCALE",
        "actual_profit_change": 150.0,  # Прибыль после масштабирования
        "decision_date": "2026-02-17"
    }
    
    print(f"  Решение пользователя:")
    print(f"    - Кампания: {user_decision['campaign_id']}")
    print(f"    - Вердикт пользователя: {user_decision['user_verdict']}")
    print(f"    - Изменение прибыли: ${user_decision['actual_profit_change']}")
    
    # В реальной системе здесь был бы вызов kb.learn_from_decision()
    print(f"\n  Система обучения:")
    print(f"    - Анализирует корреляцию голосов блоков с решением")
    print(f"    - Настраивает веса блоков")
    print(f"    - Улучшает точность будущих рекомендаций")
    
    return True


def main():
    """Основная функция демонстрации."""
    try:
        print("ДЕМОНСТРАЦИЯ СИСТЕМЫ V2 С ДИНАМИЧЕСКИМИ БЛОКАМИ")
        print("=" * 60)
        
        # Демонстрация KnowledgeBaseV2
        kb = demo_knowledge_base_v2()
        
        # Демонстрация Top5ServiceV2
        top5_service = demo_top5_service_v2()
        
        # Демонстрация системы обучения
        demo_learning_system()
        
        print(f"\n{'='*60}")
        print("ДЕМОНСТРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
        print(f"{'='*60}")
        
        print(f"\nКЛЮЧЕВЫЕ ПРЕИМУЩЕСТВА СИСТЕМЫ V2:")
        print(f"  1. Динамическая загрузка блоков из папки my_knowledge")
        print(f"  2. Голосование блоков для принятия решений")
        print(f"  3. Прозрачность: видно, какой блок как проголосовал")
        print(f"  4. Обратная совместимость с существующим кодом")
        print(f"  5. Система обучения на основе решений пользователя")
        print(f"  6. Масштабируемость: легко добавлять новые блоки")
        print(f"  7. Конфликт-разрешение: система взвешивает голоса блоков")
        
        return True
        
    except Exception as e:
        print(f"\nОшибка демонстрации: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)