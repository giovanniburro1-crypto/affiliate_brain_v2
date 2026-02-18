#!/usr/bin/env python3
"""
Тестирование системы KnowledgeBaseV2 и Top5ServiceV2.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.brain.knowledge_base_v2_complete import KnowledgeBaseV2
from backend.services.top5_service_v2_complete import Top5ServiceV2

def test_knowledgebase_v2():
    """Тестирование KnowledgeBaseV2."""
    print("🧠 Тестирование KnowledgeBaseV2...")
    
    kb = KnowledgeBaseV2()
    
    # Проверка загрузки блоков
    available_blocks = kb.get_available_blocks()
    print(f"Доступно блоков: {len(available_blocks)}")
    for block in available_blocks:
        print(f"  - {block['id']}: {block['class_name']} (enabled: {block['enabled']}, weight: {block['weight']})")
    
    # Проверка методов
    print("\n📊 Проверка методов:")
    print(f"  get_segment_columns(): {kb.get_segment_columns('facebook')}")
    print(f"  get_zacep_rules(): {kb.get_zacep_rules()}")
    print(f"  get_killer_rules(): {kb.get_killer_rules()}")
    
    # Тестирование голосования
    print("\n🗳️ Тестирование голосования блоков:")
    campaign_data = {
        "roi": 25.5,
        "profit": 1500,
        "spend": 5000,
        "clicks": 1200,
        "conversions": 45,
        "volatility": 12.3,
        "days_with_data": 7,
        "total_days": 7,
        "trend": "IMPROVING"
    }
    
    decision = kb.get_final_decision(campaign_data)
    print(f"  Финальное решение:")
    print(f"    Вердикт: {decision['final_verdict']}")
    print(f"    Уверенность: {decision['confidence']:.2%}")
    print(f"    Причина: {decision['reason']}")
    
    print(f"\n  Голоса блоков:")
    for vote in decision['votes']:
        print(f"    {vote['block_name']}: {vote['verdict']} (confidence: {vote['confidence']:.2%}, weight: {vote['weight']})")
    
    # Получение статистики
    stats = kb.get_block_statistics()
    print(f"\n📈 Статистика блоков:")
    for block_id, stat in stats.items():
        if stat['total_decisions'] > 0:
            print(f"  {block_id}: accuracy={stat['accuracy']:.2%}, weight={stat['weight']}")
    
    return kb

def test_top5_service_v2():
    """Тестирование Top5ServiceV2."""
    print("\n" + "="*60)
    print("📈 Тестирование Top5ServiceV2...")
    
    # Создаем подключение к базе данных
    from backend.config import settings
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Создаем сервис
        service = Top5ServiceV2(db)
        
        print(f"  Brain загружен: {service.brain is not None}")
        print(f"  Количество блоков: {len(service.brain.get_available_blocks())}")
        
        # Тестирование методов
        print("\n  🔍 Тестирование методов сервиса...")
        
        # Проверка сегментов
        test_segments = [
            {"type": "country", "value": "US", "spend": 1000, "revenue": 1500, "conversions": 10, "clicks": 200, "profit": 500, "roi": 50},
            {"type": "country", "value": "UK", "spend": 500, "revenue": 400, "conversions": 2, "clicks": 100, "profit": -100, "roi": -20},
        ]
        
        power_segments = service._find_power_segments(test_segments, 500, 300, limit=3)
        print(f"    Power segments: {len(power_segments)} found")
        
        weakness_segments = service._find_weakness_segments(test_segments, 1500, 500, 300, limit=5)
        print(f"    Weakness segments: {len(weakness_segments)} found")
        
        has_zacepy = service._check_zacepy(test_segments)
        print(f"    Has zacepy: {has_zacepy}")
        
        print("\n✅ Top5ServiceV2 работает корректно")
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании Top5ServiceV2: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

def main():
    """Основная функция тестирования."""
    print("🚀 Запуск тестирования системы V2")
    print("="*60)
    
    try:
        # Тестируем KnowledgeBaseV2
        kb = test_knowledgebase_v2()
        
        # Тестируем Top5ServiceV2
        test_top5_service_v2()
        
        print("\n" + "="*60)
        print("🎉 Все тесты пройдены успешно!")
        print("\nСледующие шаги:")
        print("1. Обновите роутер ai_top5.py для использования Top5ServiceV2")
        print("2. Добавьте UI элементы для показа голосов блоков")
        print("3. Запустите полное тестирование с реальными данными")
        
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())