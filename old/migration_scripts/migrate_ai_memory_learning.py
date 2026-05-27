#!/usr/bin/env python3
"""
Миграция: добавить user_comment и context_snapshot в ai_memory для обучения бота.
Запуск: cd /path/to/affiliate_brain_v2 && python3 scripts/migrate_ai_memory_learning.py
"""
import sys
sys.path.insert(0, '.')

from backend.database import engine
from sqlalchemy import text


def run():
    with engine.connect() as conn:
        for col, col_type in [("user_comment", "TEXT"), ("context_snapshot", "TEXT")]:
            try:
                conn.execute(text(f"""
                    ALTER TABLE ai_memory 
                    ADD COLUMN IF NOT EXISTS {col} {col_type}
                """))
                conn.commit()
                print(f"+ Колонка {col} добавлена (или уже была)")
            except Exception as e:
                conn.rollback()
                print(f"? Колонка {col}:", e)
    print("Готово.")


if __name__ == "__main__":
    run()
