
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
    SELECT campaign_id, SUM(cost), SUM(revenue)
    FROM traffic_stats 
    WHERE date >= ? AND date <= ? AND traffic_source = 'Moar Traffic'
    GROUP BY campaign_id
    ORDER BY SUM(cost) DESC
""", (str(date_from), str(date_to)))
rows = cursor.fetchall()

print(f"Campaigns for 'Moar Traffic': {len(rows)}")
for r in rows:
    print(r)

conn.close()
