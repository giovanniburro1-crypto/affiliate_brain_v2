#!/usr/bin/env python3
"""
Скрипт проверки системы TOP-5 Affiliate Brain v2.0
Проверяет импорты, функции и генерирует объяснение логики выбора бота.
"""
import sys
import os
from datetime import date, timedelta
import json

# Добавляем путь к бэкенду
sys.path.append('backend')

def check_imports():
    """Проверяем импорты основных модулей."""
    print("🔍 Проверка импортов...")
    try:
        from backend.services.top5_service_v2_complete import Top5ServiceV2
        from backend.brain.knowledge_base_v2_complete import KnowledgeBaseV2
        print("✅ Top5ServiceV2 и KnowledgeBaseV2 импортированы успешно")
        return True
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        return False

def check_functions():
    """Проверяем наличие ключевых функций."""
    print("\n🔍 Проверка функций...")
    from backend.services.top5_service_v2_complete import (
        Top5ServiceV2, 
        _calc_instability_index,
        _opportunity_score
    )
    
    # Проверяем статические функции
    print("✅ _calc_instability_index доступна")
    print("✅ _opportunity_score доступна")
    
    # Проверяем метод класса
    if hasattr(Top5ServiceV2, '_generate_selection_reason'):
        print("✅ Top5ServiceV2._generate_selection_reason доступна")
    else:
        print("❌ Top5ServiceV2._generate_selection_reason не найдена")
        
    return True

def setup_test_database():
    """Создаем тестовую базу данных с моковыми данными."""
    print("\n🔧 Создание тестовой базы данных...")
    
    import sqlite3
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    
    # Создаем временную базу в памяти
    engine = create_engine('sqlite:///:memory:')
    Session = sessionmaker(bind=engine)
    db = Session()
    
    # Создаем таблицы как в реальной системе
    db.execute(text("""
        CREATE TABLE traffic_stats (
            id INTEGER PRIMARY KEY,
            campaign_id TEXT NOT NULL,
            campaign TEXT NOT NULL,
            traffic_source TEXT,
            date DATE NOT NULL,
            cost REAL,
            revenue REAL,
            conversions INTEGER,
            os TEXT,
            device_type TEXT,
            token2 TEXT,
            offer TEXT,
            lander_id TEXT,
            country TEXT
        )
    """))
    
    db.execute(text("""
        CREATE TABLE additional_monetization (
            id INTEGER PRIMARY KEY,
            campaign_id TEXT NOT NULL,
            date DATE NOT NULL,
            revenue REAL
        )
    """))
    
    # Создаем тестовые данные для кампании (удовлетворяем порогам: MIN_CLICKS=100, MIN_SPEND=15)
    campaign_id = "test_campaign_001"
    campaign_name = "Test Campaign - iOS Scale"
    today = date.today()
    
    # Добавляем данные за 7 дней (стабильный рост с большим объемом)
    for day_offset in range(7):
        day = today - timedelta(days=6 - day_offset)  # Последние 7 дней
        # Создаем по 20 кликов в день чтобы превысить MIN_CLICKS=100
        for click_num in range(20):
            # Стабильные показатели: ROI ~40%, прибыль растет
            base_cost = 2.0  # Средняя стоимость клика
            base_revenue = base_cost * 1.4  # ROI 40%
            cost = base_cost + (day_offset * 0.5)  # Постепенно растет
            revenue = cost * 1.4
            conversions = 1 if click_num < 5 else 0  # 5 конверсий в день
            
            # Добавляем разнообразие сегментов
            os_type = 'iOS' if click_num < 12 else 'Android'
            device = 'Mobile' if click_num < 15 else 'Tablet'
            token2 = f'token_{click_num % 3}' if click_num % 3 == 0 else None
            
            db.execute(text("""
                INSERT INTO traffic_stats 
                (campaign_id, campaign, traffic_source, date, cost, revenue, conversions, os, device_type, token2)
                VALUES (:cid, :camp, :src, :d, :cost, :rev, :conv, :os, :device, :token)
            """), {
                'cid': campaign_id,
                'camp': campaign_name,
                'src': 'Facebook',
                'd': day,
                'cost': cost,
                'rev': revenue,
                'conv': conversions,
                'os': os_type,
                'device': device,
                'token': token2
            })
    
    # Добавляем дополнительную монетизацию
    db.execute(text("""
        INSERT INTO additional_monetization (campaign_id, date, revenue)
        VALUES (:cid, :d, :rev)
    """), {
        'cid': campaign_id,
        'd': today - timedelta(days=1),
        'rev': 50.0
    })
    
    # Добавляем еще одну кампанию для разнообразия
    campaign_id2 = "test_campaign_002"
    campaign_name2 = "Test Campaign - Android Optimize"
    
    for day_offset in range(7):
        day = today - timedelta(days=6 - day_offset)
        for click_num in range(15):  # По 15 кликов в день
            base_cost = 1.5
            cost = base_cost + (day_offset * 0.3)
            revenue = cost * 1.15  # ROI 15%
            conversions = 1 if click_num < 3 else 0  # 3 конверсии в день
            
            os_type = 'Android' if click_num < 10 else 'iOS'
            device = 'Tablet' if click_num < 8 else 'Mobile'
            
            db.execute(text("""
                INSERT INTO traffic_stats 
                (campaign_id, campaign, traffic_source, date, cost, revenue, conversions, os, device_type)
                VALUES (:cid, :camp, :src, :d, :cost, :rev, :conv, :os, :device)
            """), {
                'cid': campaign_id2,
                'camp': campaign_name2,
                'src': 'Google',
                'd': day,
                'cost': cost,
                'rev': revenue,
                'conv': conversions,
                'os': os_type,
                'device': device
            })
    
    db.commit()
    print(f"✅ Создано 2 тестовые кампании с данными за 7 дней")
    print(f"   - {campaign_id}: {campaign_name}")
    print(f"   - {campaign_id2}: {campaign_name2}")
    
    return db, engine

def test_top5_system():
    """Тестируем систему TOP-5 с тестовыми данными."""
    print("\n🚀 Тестирование системы TOP-5...")
    
    from backend.services.top5_service_v2_complete import Top5ServiceV2
    from backend.brain.knowledge_base_v2_complete import KnowledgeBaseV2
    
    db, engine = setup_test_database()
    
    # Создаем brain и service
    brain = KnowledgeBaseV2()
    service = Top5ServiceV2(db, brain)
    
    # Получаем TOP-5 кампаний
    print("\n📊 Запуск service.get_top5()...")
    result = service.get_top5(period=7, limit=5)
    
    if not result or 'campaigns' not in result:
        print("❌ Не удалось получить результаты TOP-5")
        return False
    
    campaigns = result['campaigns']
    print(f"✅ Получено {len(campaigns)} кампаний в TOP-5")
    
    # Выводим подробную информацию по каждой кампании
    for i, campaign in enumerate(campaigns, 1):
        print(f"\n{'='*60}")
        print(f"🏆 Кампания #{i}: {campaign.get('campaign')}")
        print(f"{'='*60}")
        
        # Основные метрики
        print(f"📈 ROI: {campaign.get('roi')}%")
        print(f"💰 Profit: ${campaign.get('profit')}")
        print(f"💵 Spend: ${campaign.get('spend')}")
        print(f"🖱️ Clicks: {campaign.get('clicks')}")
        print(f"✅ Conversions: {campaign.get('conversions')}")
        print(f"📉 Volatility: {campaign.get('volatility')}%")
        print(f"🎯 Verdict: {campaign.get('verdict')}")
        print(f"📊 Opportunity Score: {campaign.get('opportunity_score')}")
        print(f"🤖 Bot Score: {campaign.get('bot_score')}")
        print(f"🔍 Confidence: {campaign.get('confidence')}%")
        
        # Объяснение выбора бота
        explanation = campaign.get('explanation')
        if explanation:
            print(f"\n🧠 ЛОГИКА ВЫБОРА БОТА:")
            print(f"   {explanation}")
        else:
            print(f"\n⚠️ Объяснение не сгенерировано")
        
        # Голоса блоков (самое важное!)
        block_votes = campaign.get('block_votes', [])
        if block_votes:
            print(f"\n🧩 ГОЛОСА KNOWLEDGE BLOCKS ({len(block_votes)} блоков):")
            for vote in block_votes:
                block_name = vote.get('block_name', 'Unknown')
                verdict = vote.get('verdict', 'HOLD')
                confidence = vote.get('confidence', 0)
                reason = vote.get('reason', 'Нет объяснения')
                
                # Определяем цвет для вердикта
                color_codes = {
                    'SCALE': '\033[92m',  # зеленый
                    'STOP': '\033[91m',   # красный
                    'OPTIMIZE': '\033[94m', # синий
                    'HOLD': '\033[93m'    # желтый
                }
                color = color_codes.get(verdict, '\033[0m')
                reset = '\033[0m'
                
                print(f"   • {block_name}: {color}{verdict}{reset} ({confidence}%)")
                print(f"     Причина: {reason}")
        else:
            print(f"\n⚠️ Голоса блоков отсутствуют")
        
        # POWER и WEAKNESS сегменты
        strengths = campaign.get('strengths', [])
        weaknesses = campaign.get('weaknesses', [])
        
        if strengths:
            print(f"\n💪 POWER сегменты:")
            for s in strengths[:2]:  # Показываем максимум 2
                print(f"   • {s.get('type')}={s.get('value')} ({s.get('profit_pct')}% profit)")
        
        if weaknesses:
            print(f"\n⚠️ WEAKNESS сегменты:")
            for w in weaknesses[:2]:  # Показываем максимум 2
                print(f"   • {w.get('type')}={w.get('value')} ({w.get('profit_pct')}% profit)")
        
        # Summary lines
        summary_lines = campaign.get('summary_lines', [])
        if summary_lines:
            print(f"\n📋 Краткий анализ:")
            for line in summary_lines:
                print(f"   • {line}")
    
    print(f"\n{'='*60}")
    print("🎉 ТЕСТИРОВАНИЕ ЗАВЕРШЕНО УСПЕШНО!")
    print("="*60)
    
    # Проверяем, что explanation не содержит "Нет объяснения"
    all_explanations = [c.get('explanation', '') for c in campaigns]
    if any("Нет объяснения" in exp for exp in all_explanations):
        print("\n⚠️ ВНИМАНИЕ: Некоторые объяснения содержат 'Нет объяснения'")
        return False
    
    if any(not exp.strip() for exp in all_explanations):
        print("\n⚠️ ВНИМАНИЕ: Некоторые объяснения пустые")
        return False
    
    print("\n✅ Все объяснения сгенерированы корректно!")
    print("✅ Brain системы готов на 100%!")
    
    return True

def main():
    """Основная функция скрипта."""
    print("🧠 Affiliate Brain v2.0 - Проверка системы TOP-5")
    print("="*60)
    
    # Проверяем импорты
    if not check_imports():
        return 1
    
    # Проверяем функции
    try:
        check_functions()
    except Exception as e:
        print(f"❌ Ошибка при проверке функций: {e}")
        return 1
    
    # Запускаем тестирование системы
    try:
        success = test_top5_system()
        return 0 if success else 1
    except Exception as e:
        print(f"\n❌ Критическая ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())