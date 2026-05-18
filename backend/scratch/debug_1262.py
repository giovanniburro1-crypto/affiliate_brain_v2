
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

cursor.execute("SELECT campaign_id, token1, cost, revenue, date FROM traffic_stats WHERE token1 LIKE '%1262%' AND date >= ? AND date <= ?", (str(date_from), str(date_to)))
print("\nTraffic Stats for 1262:")
for r in cursor.fetchall():
    print(r)

cursor.execute("SELECT campaign_id, token1, revenue, date FROM additional_monetization WHERE token1 LIKE '%1262%' AND date >= ? AND date <= ?", (str(date_from), str(date_to)))
print("\nAdd Mon for 1262:")
for r in cursor.fetchall():
    print(r)

conn.close()
