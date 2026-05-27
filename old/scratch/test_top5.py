import sys
import os
sys.path.insert(0, '/Users/andreylp/affiliate_brain/app')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.services.top5_service_v2_complete import Top5ServiceV2

DATABASE_URL = 'sqlite:////Users/andreylp/affiliate_brain/database.db?timeout=60'
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

print("Starting get_top5...")
service = Top5ServiceV2(db)
try:
    res = service.get_top5(period=30, limit=5)
    print(f"Success! Found {len(res.get('campaigns', []))} campaigns")
except Exception as e:
    print(f"Error: {e}")
finally:
    db.close()
