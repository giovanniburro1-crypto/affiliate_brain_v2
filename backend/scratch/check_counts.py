
import sqlite3
from datetime import date, timedelta

db_path = "/Users/andreylp/affiliate_brain/database.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# mimic _period_or_range(14, None, None)
today = date(2026, 5, 10)
date_to = today
date_from = today - timedelta(days=14)

print(f"Period: {date_from} to {date_to}")

cursor.execute("""
    SELECT COUNT(*) FROM (
        SELECT campaign_id 
        FROM traffic_stats 
        WHERE date >= ? AND date <= ?
        GROUP BY campaign_id
        HAVING SUM(cost) >= 1 OR SUM(revenue) >= 1
    )
""", (str(date_from), str(date_to)))
print(f"Campaigns with Cost or Rev >= 1: {cursor.fetchone()[0]}")

cursor.execute("""
    SELECT COUNT(*) FROM (
        SELECT campaign_id 
        FROM traffic_stats 
        WHERE date >= ? AND date <= ?
        GROUP BY campaign_id
        HAVING (SUM(cost) > 0 AND SUM(cost) < 1) OR (SUM(revenue) > 0 AND SUM(revenue) < 1)
    )
""", (str(date_from), str(date_to)))
print(f"Campaigns with Cost or Rev > 0 but < 1: {cursor.fetchone()[0]}")

conn.close()
