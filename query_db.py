from backend.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
res = db.execute(text("SELECT DISTINCT campaign FROM traffic_stats WHERE campaign ILIKE '%stop%' LIMIT 10")).fetchall()
print(res)
