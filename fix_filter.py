import re
filepath = "/Users/andreylp/affiliate_brain/app/backend/services/top5_service_v2_complete.py"
with open(filepath, "r") as f:
    content = f.read()

old_query = "SELECT DISTINCT campaign_id FROM traffic_stats WHERE campaign LIKE '%STOP -%' OR campaign LIKE '%stop -%'"
new_query = """SELECT DISTINCT campaign_id
                    FROM traffic_stats t1
                    WHERE date = (SELECT MAX(date) FROM traffic_stats t2 WHERE t2.campaign_id = t1.campaign_id)
                      AND (campaign LIKE '%STOP -%' OR campaign LIKE '%stop -%')"""

content = content.replace(old_query, new_query)

with open(filepath, "w") as f:
    f.write(content)
