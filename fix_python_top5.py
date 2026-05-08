import re
filepath = "/Users/andreylp/affiliate_brain/app/backend/services/top5_service_v2_complete.py"
with open(filepath, "r") as f:
    content = f.read()

addition = """
        # Также исключаем кампании, у которых в имени есть "STOP - "
        try:
            stopped_rows = self.db.execute(
                text("SELECT DISTINCT campaign_id FROM traffic_stats WHERE campaign LIKE '%STOP -%'")
            ).fetchall()
            excluded_campaigns.extend([row[0] for row in stopped_rows])
            excluded_campaigns = list(set(excluded_campaigns))
        except Exception:
            pass
"""

# For get_top5
match = re.search(r'excluded_campaigns = \[row\[0\] for row in excluded_rows\]\s+except Exception:\s+# Таблицы может не существовать, игнорируем\s+pass', content)
if match:
    content = content[:match.end()] + "\n" + addition + content[match.end():]

with open(filepath, "w") as f:
    f.write(content)

