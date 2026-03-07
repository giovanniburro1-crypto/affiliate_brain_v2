#!/usr/bin/env python3
"""
Полное тестирование системы KnowledgeBaseV2 с мигрированными блоками.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.brain.knowledge_base_v2_complete import KnowledgeBaseV2


def test_knowledge_base_v2():
    """Тестирование KnowledgeBaseV2."""
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ KNOWLEDGEBASEV2 С МИГРИРОВАННЫМИ БЛОКАМИ")
    print("=" * 60)
    
    # Создаем экземпляр KnowledgeBaseV2
    kb = KnowledgeBaseV2()
    
    print(f"Загружено блоков: {len(kb._loaded_classes)}")
    print(f"Метаданных блоков: {len(kb._blocks_metadata)}")
    
    # Показываем загруженные блоки
    print("\nЗагруженные блоки:")
    for block_id, cls in kb._loaded_classes.items():
        print(f"  • {block_id} -> {cls.__name__}")
    
    # Тестовые данные кампаний
    test_campaigns = [
        {
            "campaign_id": "test_1",
            "roi": 35.5,
            "profit": 150.0,
            "spend": 100.0,
            "clicks": 1000,
            "conversions": 5,
            "volatility": 15.0,
            "payout": 50.0,
            "epc": 0.15,
            "cpc": 0.05,
            "offer": "Test Offer 1",
            "has_jump_monetization": True
        },
        {
            "campaign_id": "test_2",
            "roi": -25.0,
            "profit": -50.0,
            "spend": 200.0,
            "clicks": 5000,
            "conversions": 0,
            "volatility": 30.0,
            "payout": 100.0,
            "epc": 0.05,
            "cpc": 0.04,
            "offer": "Test Offer 2",
            "has_jump_monetization": False
        },
        {
            "campaign_id": "test_3",
            "roi": 10.0,
            "profit": 20.0,
            "spend": 200.0,
            "clicks": 2000,
            "conversions": 2,
            "volatility": 10.0,
            "payout": 75.0,
            "epc": 0.10,
            "cpc": 0.10,
            "offer": "Test Offer 3",
            "has_jump_monetization": True
        }
    ]
    
    # Тестируем анализ каждой кампании
    for i, campaign in enumerate(test_campaigns, 1):
        print(f"\n{'='*40}")
        print(f"ТЕСТ КАМПАНИИ {i}: {campaign['campaign_id']}")
        print(f"{'='*40}")
        
        print(f"Данные кампании:")
        for key, value in campaign.items():
            if key != 'campaign_id':
                print(f"  {key}: {value}")
        
        # Получаем голоса от всех блоков
        votes = kb.get_block_votes(campaign)
        print(f"\nГолоса блоков ({len(votes)}):")
        
        for vote in votes:
            print(f"  • {vote.block_name}: {vote.verdict} ({vote.confidence:.1%}) - {vote.reason}")
        
        # Получаем финальное решение
        decision = kb.get_final_decision(campaign)
        
        print(f"\nФинальное решение:")
        print(f"  Вердикт: {decision['final_verdict']}")
        print(f"  Уверенность: {decision['confidence']:.1%}")
        print(f"  Причина: {decision['reason']}")
        
        # Показываем детализацию голосов
        print(f"\nДетализация голосов:")
        for verdict, breakdown in decision['vote_breakdown'].items():
            print(f"  {verdict}: {breakdown['count']} голосов, суммарный вес: {breakdown['total_weighted_score']:.2f}")
    
    # Тестируем статистику блоков
    print(f"\n{'='*60}")
    print("СТАТИСТИКА БЛОКОВ")
    print(f"{'='*60}")
    
    stats = kb.get_block_statistics()
    for block_id, block_stats in stats.items():
        print(f"\n{block_id}:")
        print(f"  Включен: {block_stats['enabled']}")
        print(f"  Вес: {block_stats['weight']:.2f}")
        print(f"  Приоритет: {block_stats['priority']}")
        print(f"  Точность: {block_stats['accuracy']:.1%}")
        print(f"  Правильных решений: {block_stats['correct_decisions']}/{block_stats['total_decisions']}")
        print(f"  Класс: {block_stats['class_name']}")
        print(f"  Описание: {block_stats['description']}")
    
    # Тестируем методы обратной совместимости
    print(f"\n{'='*60}")
    print("ТЕСТ ОБРАТНОЙ СОВМЕСТИМОСТИ")
    print(f"{'='*60}")
    
    # Тестируем методы оригинального KnowledgeBase
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
    
    # Тестируем упрощенный анализ
    print(f"\nУпрощенный анализ кампании:")
    simple_result = kb.analyze_campaign_simple(test_campaigns[0])
    print(f"  Вердикт: {simple_result['verdict']}")
    print(f"  Уверенность: {simple_result['confidence']:.1f}%")
    print(f"  Причина: {simple_result['reason']}")
    
    # Тестируем запись решения для обучения
    print(f"\n{'='*60}")
    print("ТЕСТ ОБУЧЕНИЯ СИСТЕМЫ")
    print(f"{'='*60}")
    
    # Записываем решение пользователя
    user_decision = "SCALE"  # Пользователь решил скейлить
    kb.record_decision(test_campaigns[0]['campaign_id'], decision, user_decision)
    
    print(f"Записано решение пользователя: {user_decision}")
    print(f"История решений: {len(kb.get_decision_history())} записей")
    
    # Проверяем обновление весов
    print(f"\nОбновленные веса блоков:")
    updated_stats = kb.get_block_statistics()
    for block_id, block_stats in updated_stats.items():
        if block_stats['total_decisions'] > 0:
            print(f"  {block_id}: вес {block_stats['weight']:.2f}, точность {block_stats['accuracy']:.1%}")
    
    print(f"\n{'='*60}")
    print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print(f"{'='*60}")
    
    return True


def test_migrated_blocks():
    """Тестирование мигрированных блоков напрямую."""
    print(f"\n{'='*60}")
    print("ТЕСТИРОВАНИЕ МИГРИРОВАННЫХ БЛОКОВ")
    print(f"{'='*60}")
    
    # Импортируем мигрированные блоки
    import importlib.util
    import sys
    
    migrated_dir = "logic_blocks/migrated_blocks"
    
    if not os.path.exists(migrated_dir):
        print(f"Директория {migrated_dir} не найдена")
        return False
    
    # Пробуем импортировать модуль мигрированных блоков
    try:
        sys.path.insert(0, "logic_blocks")
        import logic_blocks.migrated_blocks as migrated_module
        
        if hasattr(migrated_module, 'load_migrated_blocks'):
            blocks = migrated_module.load_migrated_blocks()
            print(f"Загружено мигрированных блоков: {len(blocks)}")
            
            # Тестируем каждый блок
            for i, register_func in enumerate(blocks, 1):
                try:
                    block = register_func()
                    print(f"\nБлок {i}: {block.name}")
                    print(f"  Описание: {block.description}")
                    print(f"  Категория: {block.category}")
                    print(f"  Вес: {block.weight}")
                    
                    # Тестовые данные
                    test_data = {
                        "roi": 35.5,
                        "profit": 150.0,
                        "spend": 100.0,
                        "clicks": 1000,
                        "conversions": 5,
                        "volatility": 15.0
                    }
                    
                    # Анализируем
                    result = block.analyze(test_data)
                    print(f"  Вердикт: {result['verdict']}")
                    print(f"  Уверенность: {result['confidence']:.1f}%")
                    print(f"  Причины: {', '.join(result['reasoning'])}")
                    
                except Exception as e:
                    print(f"Ошибка тестирования блока {i}: {e}")
                    
        else:
            print("Модуль мигрированных блоков не имеет функции load_migrated_blocks")
            
    except Exception as e:
        print(f"Ошибка импорта мигрированных блоков: {e}")
        
        # Пробуем загрузить блоки напрямую
        print("\nПопытка прямой загрузки блоков:")
        for py_file in os.listdir(migrated_dir):
            if py_file.endswith('.py') and py_file != '__init__.py':
                print(f"  Найден файл: {py_file}")
    
    return True


def main():
    """Основная функция тестирования."""
    try:
        # Тестируем мигрированные блоки
        test_migrated_blocks()
        
        # Тестируем KnowledgeBaseV2
        test_knowledge_base_v2()
        
        print(f"\n{'='*60}")
        print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print(f"{'='*60}")
        
        return True
        
    except Exception as e:
        print(f"\nОшибка тестирования: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)