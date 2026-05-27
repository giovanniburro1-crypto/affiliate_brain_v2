#!/usr/bin/env python3
"""
Миграция: добавить click_id в additional_monetization, очистить таблицу.
Запуск: cd /Users/andreylp/Desktop/affiliate_brain_v2 && python3 scripts/migrate_add_click_id.py
"""
import sys
sys.path.insert(0, '.')

from backend.database import engine
from sqlalchemy import text

def run():
    with engine.connect() as conn:
        # 1. Добавить колонку click_id (если нет)
        try:
            conn.execute(text("""
                ALTER TABLE additional_monetization 
                ADD COLUMN IF NOT EXISTS click_id VARCHAR(255)
            """))
            conn.commit()
            print("+ Колонка click_id добавлена (или уже была)")
        except Exception as e:
            conn.rollback()
            print("? Колонка:", e)

        # 2. Уникальный constraint на click_id (для ON CONFLICT). NULL допустимы для sale-файлов
        try:
            conn.execute(text("ALTER TABLE additional_monetization DROP CONSTRAINT IF EXISTS uq_add_mon_click_id"))
            conn.execute(text("""
                ALTER TABLE additional_monetization 
                ADD CONSTRAINT uq_add_mon_click_id UNIQUE (click_id)
            """))
            conn.commit()
            print("+ Уникальный constraint на click_id создан")
        except Exception as e:
            conn.rollback()
            print("? Constraint:", e)

        # 3. Очистить таблицу
        conn.execute(text("TRUNCATE TABLE additional_monetization CASCADE"))
        conn.commit()
        print("+ Таблица additional_monetization очищена")

    print("Готово. Загрузите файлы и проверьте.")

if __name__ == "__main__":
    run()
