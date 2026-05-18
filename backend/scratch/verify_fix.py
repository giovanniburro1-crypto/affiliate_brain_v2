
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

# Moar Traffic filter
source_filter = "AND traffic_source = 'Moar Traffic'"

query = f"""
    WITH all_cids AS (
        SELECT DISTINCT campaign_id FROM traffic_stats 
        WHERE date >= ? AND date <= ? AND campaign_id IS NOT NULL {source_filter}
        UNION
        SELECT DISTINCT campaign_id FROM additional_monetization
        WHERE date >= ? AND date <= ? AND campaign_id IS NOT NULL
          AND campaign_id IN (SELECT DISTINCT campaign_id FROM traffic_stats WHERE date >= ? AND date <= ? {source_filter})
    ),
    campaign_base AS (
        SELECT 
            ts.campaign_id, 
            MAX(ts.token1) as token1, 
            SUM(ts.cost) as total_spend,
            SUM(ts.revenue) as base_revenue
        FROM traffic_stats ts
        JOIN all_cids ac ON ts.campaign_id = ac.campaign_id
        WHERE ts.date >= ? AND ts.date <= ? {source_filter}
        GROUP BY ts.campaign_id
    ),
    campaign_add AS (
        SELECT 
            am.campaign_id,
            SUM(am.revenue) as add_revenue
        FROM additional_monetization am
        JOIN all_cids ac ON am.campaign_id = ac.campaign_id
        WHERE am.date >= ? AND am.date <= ?
        GROUP BY am.campaign_id
    )
    SELECT 
        ac.campaign_id, 
        cb.token1, 
        COALESCE(cb.total_spend, 0) as total_spend,
        (COALESCE(cb.base_revenue, 0) + COALESCE(ca.add_revenue, 0)) as total_rev
    FROM all_cids ac
    LEFT JOIN campaign_base cb ON ac.campaign_id = cb.campaign_id
    LEFT JOIN campaign_add ca ON ac.campaign_id = ca.campaign_id
    WHERE ROUND(COALESCE(cb.total_spend, 0)) >= 1 OR ROUND(COALESCE(cb.base_revenue, 0) + COALESCE(ca.add_revenue, 0)) >= 1
    ORDER BY total_spend DESC, total_rev DESC
    LIMIT 25
"""

params = (str(date_from), str(date_to)) * 5
cursor.execute(query, params)
rows = cursor.fetchall()

print(f"Filtered Campaigns for 'Moar Traffic': {len(rows)}")
for r in rows:
    print(r)

conn.close()
