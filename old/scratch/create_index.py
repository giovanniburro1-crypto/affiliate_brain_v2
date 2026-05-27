import sys
import os
sys.path.insert(0, '/Users/andreylp/affiliate_brain/app')

from sqlalchemy import create_engine, text

DATABASE_URL = 'sqlite:////Users/andreylp/affiliate_brain/database.db?timeout=60'
engine = create_engine(DATABASE_URL)

print("Attempting to create index...")
try:
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL;"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ts_cid_date ON traffic_stats (campaign_id, date);"))
        conn.commit()
    print("Success!")
except Exception as e:
    print(f"Error: {e}")
