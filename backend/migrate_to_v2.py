"""
Скрипт миграции для перехода на KnowledgeBaseV2.
Создает новые таблицы и переносит данные из старой системы.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from backend.database import engine, Base
from backend.models_v2 import (
    AIMemoryV2, BlockKnowledge, BlockVoteHistory, LearningCycle,
    TrafficStats, AdditionalMonetization, Orphan, RecheckQueue, AIAgent
)
from backend.models import AIMemory as OldAIMemory
import json
from datetime import datetime, timedelta

def create_tables():
    """Создать новые таблицы для KnowledgeBaseV2."""
    print("Создание таблиц KnowledgeBaseV2...")
    
    try:
        # Создаем все таблицы из models_v2
        Base.metadata.create_all(bind=engine)
        print("✅ Таблицы успешно созданы")
        return True
    except Exception as e:
        print(f"❌ Ошибка при создании таблиц: {e}")
        return False

def migrate_ai_memory_data():
    """Перенести данные из старой таблицы ai_memory в новую ai_memory_v2."""
    print("Миграция данных из ai_memory в ai_memory_v2...")
    
    try:
        with engine.connect() as conn:
            # Проверяем, есть ли данные в старой таблице
            result = conn.execute(text("SELECT COUNT(*) FROM ai_memory"))
            old_count = result.scalar()
            
            if old_count == 0:
                print("✅ В старой таблице нет данных для миграции")
                return True
            
            print(f"Найдено {old_count} записей для миграции")
            
            # Получаем все записи из старой таблицы
            result = conn.execute(text("""
                SELECT 
                    campaign_id, decision_date, bot_verdict, bot_score, 
                    bot_confidence, bot_reasoning, ai_verdict, ai_confidence,
                    user_choice, user_comment, context_snapshot, outcome,
                    roi_after_7days, roi_after_14days
                FROM ai_memory
                ORDER BY decision_date
            """))
            
            migrated_count = 0
            for row in result:
                campaign_id = row[0]
                decision_date = row[1]
                
                # Определяем финальный вердикт (предпочтение: user_choice > ai_verdict > bot_verdict)
                final_verdict = None
                final_confidence = 0.5
                
                if row[8]:  # user_choice
                    final_verdict = row[8].upper()
                elif row[6]:  # ai_verdict
                    final_verdict = row[6].upper()
                    final_confidence = row[7] or 0.5
                elif row[2]:  # bot_verdict
                    final_verdict = row[2].upper()
                    final_confidence = row[4] or 0.5
                
                if not final_verdict:
                    final_verdict = "HOLD"
                
                # Создаем запись в новой таблице
                insert_stmt = text("""
                    INSERT INTO ai_memory_v2 (
                        campaign_id, decision_date, final_verdict, final_confidence,
                        final_reason, user_verdict, user_comment, campaign_snapshot,
                        outcome_verdict, outcome_roi_7d, outcome_roi_14d,
                        needs_outcome_update, is_training_example
                    ) VALUES (
                        :campaign_id, :decision_date, :final_verdict, :final_confidence,
                        :final_reason, :user_verdict, :user_comment, :campaign_snapshot,
                        :outcome_verdict, :outcome_roi_7d, :outcome_roi_14d,
                        :needs_outcome_update, :is_training_example
                    )
                """)
                
                conn.execute(insert_stmt, {
                    "campaign_id": campaign_id,
                    "decision_date": decision_date,
                    "final_verdict": final_verdict,
                    "final_confidence": final_confidence,
                    "final_reason": row[5] or "Мигрировано из старой системы",
                    "user_verdict": row[8] or None,
                    "user_comment": row[9] or None,
                    "campaign_snapshot": row[10] or json.dumps({"migrated": True}),
                    "outcome_verdict": row[11] or None,
                    "outcome_roi_7d": row[12] or None,
                    "outcome_roi_14d": row[13] or None,
                    "needs_outcome_update": row[12] is None,  # Нужно обновить, если нет ROI
                    "is_training_example": True
                })
                
                migrated_count += 1
                
                if migrated_count % 100 == 0:
                    print(f"  Мигрировано {migrated_count} записей...")
            
            conn.commit()
            print(f"✅ Успешно мигрировано {migrated_count} записей")
            return True
            
    except Exception as e:
        print(f"❌ Ошибка при миграции данных: {e}")
        return False

def initialize_block_knowledge():
    """Инициализировать таблицу block_knowledge на основе существующих блоков."""
    print("Инициализация таблицы block_knowledge...")
    
    try:
        # Импортируем KnowledgeBaseV2 для сканирования блоков
        from backend.brain.knowledge_base_v2 import KnowledgeBaseV2
        
        kb = KnowledgeBaseV2()
        blocks = kb.get_available_blocks()
        
        with engine.connect() as conn:
            for block in blocks:
                # Проверяем, существует ли уже блок
                check_stmt = text("SELECT COUNT(*) FROM block_knowledge WHERE block_id = :block_id")
                result = conn.execute(check_stmt, {"block_id": block["id"]})
                exists = result.scalar() > 0
                
                if not exists:
                    # Создаем новую запись
                    insert_stmt = text("""
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
                    """)
                    
                    conn.execute(insert_stmt, {
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
        print(f"❌ Ошибка при инициализации block_knowledge: {e}")
        return False

def create_initial_learning_cycle():
    """Создать начальный цикл обучения."""
    print("Создание начального цикла обучения...")
    
    try:
        with engine.connect() as conn:
            # Проверяем, есть ли уже активные циклы
            check_stmt = text("SELECT COUNT(*) FROM learning_cycles WHERE is_completed = FALSE")
            result = conn.execute(check_stmt)
            active_cycles = result.scalar()
            
            if active_cycles == 0:
                # Создаем новый цикл
                insert_stmt = text("""
                    INSERT INTO learning_cycles (
                        cycle_start, cycle_end, total_decisions, correct_decisions,
                        system_accuracy, weight_updates, avg_confidence,
                        consensus_level, is_completed, notes
                    ) VALUES (
                        :cycle_start, :cycle_end, :total_decisions, :correct_decisions,
                        :system_accuracy, :weight_updates, :avg_confidence,
                        :consensus_level, :is_completed, :notes
                    )
                """)
                
                conn.execute(insert_stmt, {
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

def backup_old_tables():
    """Создать бекап старых таблиц перед миграцией."""
    print("Создание бекапа старых таблиц...")
    
    try:
        with engine.connect() as conn:
            # Создаем бекапные таблицы
            backup_tables = [
                ("ai_memory_backup", "ai_memory"),
                ("ai_agents_backup", "ai_agents"),
                ("recheck_queue_backup", "recheck_queue")
            ]
            
            for backup_name, original_name in backup_tables:
                # Проверяем, существует ли уже бекап
                check_stmt = text(f"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='{backup_name}'")
                result = conn.execute(check_stmt)
                exists = result.scalar() > 0
                
                if not exists:
                    # Создаем бекапную таблицу
                    conn.execute(text(f"CREATE TABLE {backup_name} AS SELECT * FROM {original_name}"))
                    print(f"  Создан бекап: {backup_name}")
                else:
                    print(f"  Бекап уже существует: {backup_name}")
            
            conn.commit()
            print("✅ Бекапы успешно созданы")
            return True
            
    except Exception as e:
        print(f"❌ Ошибка при создании бекапов: {e}")
        return False

def main():
    """Основная функция миграции."""
    print("=" * 60)
    print("МИГРАЦИЯ НА KNOWLEDGEBASE V2")
    print("=" * 60)
    
    steps = [
        ("Создание бекапов", backup_old_tables),
        ("Создание таблиц", create_tables),
        ("Миграция данных AI памяти", migrate_ai_memory_data),
        ("Инициализация блоков знаний", initialize_block_knowledge),
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