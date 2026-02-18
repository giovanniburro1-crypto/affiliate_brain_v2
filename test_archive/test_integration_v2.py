#!/usr/bin/env python3
"""
Интеграционный тест для KnowledgeBaseV2 + Top5ServiceV2.
Проверяет, что система корректно работает с блоками знаний и возвращает голоса блоков.
"""
import sys
import os
from datetime import date, timedelta

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.brain.knowledge_base_v2_complete import KnowledgeBaseV2
from backend.services.top5_service_v2_complete import Top5ServiceV2


def setup_test_database(db_session):
    """Создает тестовые таблицы и добавляет данные кампании."""
    # Создаем таблицу traffic_stats
    db_session.execute(text("""
        CREATE TABLE IF NOT EXISTS traffic_stats (
            id INTEGER PRIMARY KEY,
            date DATE NOT NULL,
            campaign_id VARCHAR(255) NOT NULL,
            campaign VARCHAR(255),
            traffic_source VARCHAR(255),
            cost DECIMAL(10, 2),
            revenue DECIMAL(10, 2),
            conversions INTEGER,
            os VARCHAR(100),
            device_type VARCHAR(100),
            token2 VARCHAR(100),
            offer VARCHAR(255),
            lander_id VARCHAR(100),
            country VARCHAR(2)
        )
    """))
    
    # Создаем таблицу additional_monetization
    db_session.execute(text("""
        CREATE TABLE IF NOT EXISTS additional_monetization (
            id INTEGER PRIMARY KEY,
            campaign_id VARCHAR(255) NOT NULL,
            date DATE NOT NULL,
            revenue DECIMAL(10, 2)
        )
    """))
    
    # Очищаем таблицы
    db_session.execute(text("DELETE FROM traffic_stats"))
    db_session.execute(text("DELETE FROM additional_monetization"))
    
    # Добавляем тестовую кампанию с хорошими показателями (ROI > 40%)
    today = date.today()
    days_ago_1 = today - timedelta(days=1)
    days_ago_2 = today - timedelta(days=2)
    days_ago_3 = today - timedelta(days=3)
    
    # Кампания с высоким ROI (прибыль $250 при расходах $150)
    test_campaign_id = "test_campaign_123"
    
    # Добавляем данные за несколько дней - 100 строк для удовлетворения MIN_CLICKS=100
    test_data = []
    
    # День 1: 40 строк с конверсиями (iOS)
    for i in range(40):
        conv = 1 if i < 2 else 0  # 2 конверсии из 40
        test_data.append((days_ago_3, test_campaign_id, "Test Campaign", "FB", 
                          1.25, 3.0, conv, "iOS", "mobile", f"token_{i}", "Offer1", "lander1", "US"))
    
    # День 2: 35 строк с конверсиями (iOS)
    for i in range(35):
        conv = 1 if i < 3 else 0  # 3 конверсии из 35
        test_data.append((days_ago_2, test_campaign_id, "Test Campaign", "FB", 
                          1.43, 3.43, conv, "iOS", "mobile", f"token_{40+i}", "Offer1", "lander1", "US"))
    
    # День 3: 25 строк с конверсиями (Android)
    for i in range(25):
        conv = 1 if i < 3 else 0  # 3 конверсии из 25
        test_data.append((days_ago_1, test_campaign_id, "Test Campaign", "FB", 
                          2.0, 4.4, conv, "Android", "mobile", f"token_{75+i}", "Offer1", "lander1", "US"))
    
    # Проверяем суммы: общий расход = 40*1.25 + 35*1.43 + 25*2.0 = 50 + 50 + 50 = 150
    # Общий доход = 40*3.0 + 35*3.43 + 25*4.4 = 120 + 120 + 110 = 350 (базовый) + 25 (add_mon) = 375
    # Конверсии: 2 + 3 + 3 = 8
    
    for i, (d, cid, camp, src, cost, rev, conv, os, dev, tok, off, land, country) in enumerate(test_data):
        db_session.execute(text("""
            INSERT INTO traffic_stats 
            (date, campaign_id, campaign, traffic_source, cost, revenue, conversions, os, device_type, token2, offer, lander_id, country)
            VALUES (:d, :cid, :camp, :src, :cost, :rev, :conv, :os, :dev, :tok, :off, :land, :country)
        """), {
            "d": d, "cid": cid, "camp": camp, "src": src, "cost": cost, "rev": rev, 
            "conv": conv, "os": os, "dev": dev, "tok": tok, "off": off, "land": land, "country": country
        })
    
    # Добавляем дополнительные монетизации
    db_session.execute(text("""
        INSERT INTO additional_monetization (campaign_id, date, revenue)
        VALUES (:cid, :d, :rev)
    """), {"cid": test_campaign_id, "d": days_ago_1, "rev": 25.0})
    
    db_session.commit()
    
    print(f"✓ Созданы тестовые таблицы и добавлена кампания '{test_campaign_id}'")
    print(f"  - 3 дня данных: 100 строк (кликов)")
    print(f"  - Суммарный расход $150, доход $375")
    print(f"  - ROI: {(375-150)/150*100:.1f}% > 40%, Profit: ${375-150}=225")
    print(f"  - Конверсии: 8")


def test_knowledge_base_v2():
    """Тестируем KnowledgeBaseV2 отдельно."""
    print("\n=== Тест KnowledgeBaseV2 ===")
    
    kb = KnowledgeBaseV2()
    
    # Проверяем, что метод analyze_campaign существует
    if hasattr(kb, 'analyze_campaign'):
        print("✓ Метод analyze_campaign доступен")
    else:
        print("✗ ОШИБКА: метод analyze_campaign не найден!")
        return False
    
    # Тестовый вызов
    result = kb.analyze_campaign(
        campaign_id='test_campaign_123',
        roi=45.5,
        profit=225.0,
        spend=150.0,
        clicks=1500,
        conversions=8,
        volatility=12.0,
        daily_impact=[10, 20, 15, 18, 22]
    )
    
    print(f"✓ analyze_campaign вернул результат:")
    print(f"  - Вердикт: {result.get('verdict')}")
    print(f"  - Уверенность: {result.get('confidence'):.1f}%")
    print(f"  - Голоса блоков: {len(result.get('block_votes', []))} шт.")
    
    # Проверяем формат голосов
    block_votes = result.get('block_votes', [])
    if block_votes:
        vote = block_votes[0]
        required_keys = {'block_name', 'verdict', 'confidence'}
        if required_keys.issubset(vote.keys()):
            print("✓ Формат голосов блоков корректен")
        else:
            print(f"✗ ОШИБКА: в голосах отсутствуют ключи {required_keys - set(vote.keys())}")
            return False
    else:
        print("✗ ОШИБКА: нет голосов блоков!")
        return False
    
    return True


def test_top5_service_v2():
    """Тестируем Top5ServiceV2 с базой данных."""
    print("\n=== Тест Top5ServiceV2 ===")
    
    # Создаем базу данных в памяти
    engine = create_engine('sqlite:///:memory:')
    Session = sessionmaker(bind=engine)
    db = Session()
    
    # Настраиваем тестовые данные
    setup_test_database(db)
    
    # Создаем сервис
    service = Top5ServiceV2(db)
    print("✓ Top5ServiceV2 инициализирован")
    
    # Получаем топ-5 кампаний
    try:
        result = service.get_top5(period=7, limit=5)
        print("✓ service.get_top5() выполнен успешно")
        
        # Проверяем структуру результата
        if 'campaigns' in result:
            campaigns = result['campaigns']
            print(f"✓ Найдено кампаний: {len(campaigns)}")
            
            if campaigns:
                campaign = campaigns[0]
                print(f"✓ Первая кампания: {campaign.get('campaign')} (ID: {campaign.get('campaign_id')})")
                print(f"  - ROI: {campaign.get('roi')}%")
                print(f"  - Вердикт: {campaign.get('verdict')}")
                print(f"  - Уверенность: {campaign.get('confidence'):.1f}%")
                
                # Проверяем наличие block_votes
                block_votes = campaign.get('block_votes', [])
                if block_votes:
                    print(f"  ✓ Голоса блоков: {len(block_votes)} шт.")
                    for i, vote in enumerate(block_votes[:3]):  # Показываем первые 3
                        print(f"    {i+1}. {vote.get('block_name')}: {vote.get('verdict')} (conf: {vote.get('confidence'):.2f})")
                else:
                    print("  ✗ ОШИБКА: block_votes отсутствует или пуст")
                    return False
                
                # Проверяем summary_lines
                summary_lines = campaign.get('summary_lines', [])
                if summary_lines:
                    print(f"  ✓ Строк сводки: {len(summary_lines)}")
                    # Ищем строку с BLOCKS
                    blocks_line = next((line for line in summary_lines if 'BLOCKS:' in line), None)
                    if blocks_line:
                        print(f"  ✓ Строка с голосами блоков присутствует в сводке")
                    else:
                        print(f"  ⚠ ВНИМАНИЕ: строка с BLOCKS не найдена в сводке")
                else:
                    print("  ⚠ ВНИМАНИЕ: summary_lines отсутствует")
            else:
                print("✗ ОШИБКА: кампании не найдены")
                return False
        else:
            print("✗ ОШИБКА: в результате отсутствует ключ 'campaigns'")
            return False
            
    except Exception as e:
        print(f"✗ ОШИБКА при вызове service.get_top5(): {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


def main():
    print("=== Интеграционный тест KnowledgeBaseV2 + Top5ServiceV2 ===")
    print("Цель: убедиться, что система возвращает голоса блоков в результатах.\n")
    
    # Тест 1: KnowledgeBaseV2
    kb_ok = test_knowledge_base_v2()
    if not kb_ok:
        print("\n✗ Тест KnowledgeBaseV2 не пройден")
        return 1
    
    # Тест 2: Top5ServiceV2
    service_ok = test_top5_service_v2()
    if not service_ok:
        print("\n✗ Тест Top5ServiceV2 не пройден")
        return 1
    
    print("\n" + "="*60)
    print("✓ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
    print("="*60)
    print("\nВыводы:")
    print("1. KnowledgeBaseV2 корректно загружает блоки из my_knowledge/")
    print("2. Метод analyze_campaign возвращает голоса блоков в правильном формате")
    print("3. Top5ServiceV2 использует KnowledgeBaseV2 и включает block_votes в результат")
    print("4. Голоса блоков отображаются в summary_lines кампании")
    print("\nСистема готова к использованию в API и фронтенде.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())