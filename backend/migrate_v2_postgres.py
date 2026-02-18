"""
Скрипт миграции для PostgreSQL для создания таблиц KnowledgeBaseV2.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
import json
from datetime import datetime

def check_table_exists(conn, table_name):
    """Проверить существование таблицы."""
    result = conn.execute(text(f"""
        SELECT COUNT(*) FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = '{table_name}'
    """))
    return result.scalar() > 0

def create_v2_tables():
    """Создать таблицы для KnowledgeBaseV2."""
    print("Создание таблиц KnowledgeBaseV2...")
    
    try:
        from backend.database import engine
        
        with engine.connect() as conn:
            # Создаем таблицу ai_memory_v2
            if not check_table_exists(conn, "ai_memory_v2"):
                conn.execute(text("""
                    CREATE TABLE ai_memory_v2 (
                        id SERIAL PRIMARY KEY,
                        campaign_id VARCHAR(100) NOT NULL,
                        decision_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        
                        -- Голоса блоков
                        block_votes JSONB,
                        final_verdict VARCHAR(50),
                        final_confidence FLOAT,
                        final_reason TEXT,
                        
                        -- Решение пользователя
                        user_verdict VARCHAR(50),
                        user_comment TEXT,
                        
                        -- Контекст кампании
                        campaign_snapshot JSONB,
                        metrics_snapshot JSONB,
                        
                        -- Результаты
                        outcome_verdict VARCHAR(50),
                        outcome_roi_7d FLOAT,
                        outcome_roi_14d FLOAT,
                        outcome_updated_at TIMESTAMP,
                        
                        -- Флаги
                        needs_outcome_update BOOLEAN DEFAULT TRUE,
                        is_training_example BOOLEAN DEFAULT TRUE
                    )
                """))
                
                # Создаем индексы
                conn.execute(text("""
                    CREATE INDEX ix_ai_memory_v2_campaign_date 
                    ON ai_memory_v2 (campaign_id, decision_date)
                """))
                conn.execute(text("""
                    CREATE INDEX ix_ai_memory_v2_outcome 
                    ON ai_memory_v2 (outcome_verdict)
                """))
                conn.execute(text("""
                    CREATE INDEX ix_ai_memory_v2_needs_update 
                    ON ai_memory_v2 (needs_outcome_update)
                """))
                print("✅ Создана таблица ai_memory_v2")
            else:
                print("✅ Таблица ai_memory_v2 уже существует")
            
            # Создаем таблицу block_knowledge
            if not check_table_exists(conn, "block_knowledge"):
                conn.execute(text("""
                    CREATE TABLE block_knowledge (
                        id SERIAL PRIMARY KEY,
                        block_id VARCHAR(100) UNIQUE NOT NULL,
                        block_name VARCHAR(255),
                        class_name VARCHAR(255),
                        description TEXT,
                        
                        -- Веса и приоритеты
                        current_weight FLOAT DEFAULT 1.0,
                        base_weight FLOAT DEFAULT 1.0,
                        priority INTEGER DEFAULT 5,
                        enabled BOOLEAN DEFAULT TRUE,
                        
                        -- Статистика
                        total_votes INTEGER DEFAULT 0,
                        correct_votes INTEGER DEFAULT 0,
                        accuracy FLOAT DEFAULT 0.0,
                        
                        -- История весов
                        weight_history JSONB,
                        
                        -- Временные метки
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_used TIMESTAMP,
                        last_weight_update TIMESTAMP,
                        
                        -- Дополнительные метаданные
                        block_metadata JSONB
                    )
                """))
                
                # Создаем индексы
                conn.execute(text("""
                    CREATE INDEX ix_block_knowledge_block_id 
                    ON block_knowledge (block_id)
                """))
                conn.execute(text("""
                    CREATE INDEX ix_block_knowledge_enabled 
                    ON block_knowledge (enabled)
                """))
                conn.execute(text("""
                    CREATE INDEX ix_block_knowledge_priority 
                    ON block_knowledge (priority)
                """))
                print("✅ Создана таблица block_knowledge")
            else:
                print("✅ Таблица block_knowledge уже существует")
            
            # Создаем таблицу block_vote_history
            if not check_table_exists(conn, "block_vote_history"):
                conn.execute(text("""
                    CREATE TABLE block_vote_history (
                        id SERIAL PRIMARY KEY,
                        decision_id INTEGER NOT NULL,
                        block_id VARCHAR(100) NOT NULL,
                        
                        -- Голос блока
                        verdict VARCHAR(50),
                        confidence FLOAT,
                        reason TEXT,
                        weight_at_time FLOAT,
                        
                        -- Результат
                        was_correct BOOLEAN,
                        user_verdict VARCHAR(50),
                        
                        -- Временные метки
                        voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                
                # Создаем индексы
                conn.execute(text("""
                    CREATE INDEX ix_block_vote_history_decision_block 
                    ON block_vote_history (decision_id, block_id)
                """))
                conn.execute(text("""
                    CREATE INDEX ix_block_vote_history_was_correct 
                    ON block_vote_history (was_correct)
                """))
                conn.execute(text("""
                    CREATE INDEX ix_block_vote_history_block_id 
                    ON block_vote_history (block_id)
                """))
                print("✅ Создана таблица block_vote_history")
            else:
                print("✅ Таблица block_vote_history уже существует")
            
            # Создаем таблицу learning_cycles
            if not check_table_exists(conn, "learning_cycles"):
                conn.execute(text("""
                    CREATE TABLE learning_cycles (
                        id SERIAL PRIMARY KEY,
                        cycle_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        cycle_end TIMESTAMP,
                        
                        -- Статистика цикла
                        total_decisions INTEGER DEFAULT 0,
                        correct_decisions INTEGER DEFAULT 0,
                        system_accuracy FLOAT DEFAULT 0.0,
                        
                        -- Изменения весов
                        weight_updates JSONB,
                        
                        -- Метрики
                        avg_confidence FLOAT DEFAULT 0.0,
                        consensus_level FLOAT DEFAULT 0.0,
                        
                        -- Флаги
                        is_completed BOOLEAN DEFAULT FALSE,
                        
                        -- Комментарии
                        notes TEXT
                    )
                """))
                
                # Создаем индексы
                conn.execute(text("""
                    CREATE INDEX ix_learning_cycles_is_completed 
                    ON learning_cycles (is_completed)
                """))
                conn.execute(text("""
                    CREATE INDEX ix_learning_cycles_cycle_start 
                    ON learning_cycles (cycle_start)
                """))
                print("✅ Создана таблица learning_cycles")
            else:
                print("✅ Таблица learning_cycles уже существует")
            
            conn.commit()
            print("\n✅ Все таблицы KnowledgeBaseV2 успешно созданы")
            return True
            
    except Exception as e:
        print(f"❌ Ошибка при создании таблиц: {e}")
        return False

def initialize_blocks():
    """Инициализировать блоки знаний."""
    print("\nИнициализация блоков знаний...")
    
    try:
        from backend.brain.knowledge_base_v2 import KnowledgeBaseV2
        from backend.database import engine
        
        kb = KnowledgeBaseV2()
        blocks = kb.get_available_blocks()
        
        with engine.connect() as conn:
            for block in blocks:
                # Проверяем, существует ли уже блок
                result = conn.execute(
                    text("SELECT COUNT(*) FROM block_knowledge WHERE block_id = :block_id"),
                    {"block_id": block["id"]}
                )
                exists = result.scalar() > 0
                
                if not exists:
                    # Создаем новую запись
                    conn.execute(text("""
                        INSERT INTO block_knowledge (
                            block_id, block_name, class_name, description,
                            current_weight, base_weight, priority, enabled,
                            total_votes, correct_votes, accuracy,
                            created_at, last_used, block_metadata
                        ) VALUES (
                            :block_id, :block_name, :class_name, :description,
                            :current_weight, :base_weight, :priority, :enabled,
                            :total_votes, :correct_votes, :accuracy,
                            :created_at, :last_used, :block_metadata
                        )
                    """), {
                        "block_id": block["id"],
                        "block_name": block["id"].replace("_", " ").title(),
                        "class_name": block["class_name"],
                        "description": block.get("description", f"Блок знаний {block['id']}"),
                        "current_weight": 1.0,
                        "base_weight": 1.0,
                        "priority": 5,
                        "enabled": block.get("enabled", True),
                        "total_votes": 0,
                        "correct_votes": 0,
                        "accuracy": 0.0,
                        "created_at": datetime.now(),
                        "last_used": None,
                        "block_metadata": json.dumps({
                            "loaded": block.get("loaded", False),
                            "file_path": f"logic_blocks/my_knowledge/{block['id']}.py"
                        })
                    })
                    print(f"  Добавлен блок: {block['id']}")
            
            conn.commit()
            print(f"✅ Инициализировано {len(blocks)} блоков знаний")
            return True
            
    except Exception as e:
        print(f"❌ Ошибка при инициализации блоков: {e}")
        return False

def create_initial_learning_cycle():
    """Создать начальный цикл обучения."""
    print("\nСоздание начального цикла обучения...")
    
    try:
        from backend.database import engine
        
        with engine.connect() as conn:
            # Проверяем, есть ли уже активные циклы
            result = conn.execute(text("SELECT COUNT(*) FROM learning_cycles WHERE is_completed = FALSE"))
            active_cycles = result.scalar()
            
            if active_cycles == 0:
                # Создаем новый цикл
                conn.execute(text("""
                    INSERT INTO learning_cycles (
                        cycle_start, cycle_end, total_decisions, correct_decisions,
                        system_accuracy, weight_updates, avg_confidence,
                        consensus_level, is_completed, notes
                    ) VALUES (
                        :cycle_start, :cycle_end, :total_decisions, :correct_decisions,
                        :system_accuracy, :weight_updates, :avg_confidence,
                        :consensus_level, :is_completed, :notes
                    )
                """), {
                    "cycle_start": datetime.now(),
                    "cycle_end": None,
                    "total_decisions": 0,
                    "correct_decisions": 0,
                    "system_accuracy": 0.0,
                    "weight_updates": json.dumps({}),
                    "avg_confidence": 0.0,
                    "consensus_level": 0.0,
                    "is_completed": False,
                    "notes": "Начальный цикл обучения после миграции на KnowledgeBaseV2"
                })
                
                conn.commit()
                print("✅ Создан начальный цикл обучения")
            else:
                print("✅ Активные циклы обучения уже существуют")
            
            return True
            
    except Exception as e:
        print(f"❌ Ошибка при создании цикла обучения: {e}")
        return False

def main():
    """Основная функция миграции."""
    print("=" * 60)
    print("МИГРАЦИЯ НА KNOWLEDGEBASE V2 (POSTGRESQL)")
    print("=" * 60)
    
    steps = [
        ("Создание таблиц V2", create_v2_tables),
        ("Инициализация блоков знаний", initialize_blocks),
        ("Создание цикла обучения", create_initial_learning_cycle),
    ]
    
    success = True
    for step_name, step_func in steps:
        print(f"\n📋 Шаг: {step_name}")
        if not step_func():
            success = False
            print(f"❌ Шаг '{step_name}' завершился с ошибкой")
            break
    
    print("\n" + "=" * 60)
    if success:
        print("✅ МИГРАЦИЯ УСПЕШНО ЗАВЕРШЕНА")
        print("\nСледующие шаги:")
        print("1. Обновите top5_service.py для использования KnowledgeBaseV2")
        print("2. Добавьте UI элементы для показа голосов блоков")
        print("3. Запустите тестирование системы")
    else:
        print("❌ МИГРАЦИЯ ЗАВЕРШИЛАСЬ С ОШИБКОЙ")
        print("\nРекомендации:")
        print("1. Проверьте логи ошибок выше")
        print("2. Убедитесь, что база данных доступна")
        print("3. Проверьте права доступа к файлам")
    
    print("=" * 60)

if __name__ == "__main__":
    main()