#!/usr/bin/env python3
"""
Создание таблицы recheck_queue для очереди речека кампаний.
Запуск: из корня проекта: python3 scripts/create_recheck_queue.py
"""
import sys
sys.path.insert(0, '.')

from backend.database import engine
from sqlalchemy import text

# PostgreSQL
SQL = """
CREATE TABLE IF NOT EXISTS recheck_queue (
    id SERIAL PRIMARY KEY,
    campaign_id VARCHAR(100) NOT NULL,
    campaign VARCHAR(255),
    verdict VARCHAR(50),
    recheck_after_days INTEGER DEFAULT 0,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def run():
    with engine.connect() as conn:
        conn.execute(text(SQL))
        conn.commit()
        print("+ Таблица recheck_queue создана (или уже существует)")

if __name__ == "__main__":
    run()
