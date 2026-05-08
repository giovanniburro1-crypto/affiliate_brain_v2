import re
filepath = "/Users/andreylp/affiliate_brain/app/backend/services/top5_service_v2_complete.py"
with open(filepath, "r") as f:
    content = f.read()

addition = """
        # Также исключаем кампании, у которых в имени есть "STOP - "
        try:
            stopped_rows = self.db.execute(
                text("SELECT DISTINCT campaign_id FROM traffic_stats WHERE campaign LIKE '%STOP -%' OR campaign LIKE '%stop -%'")
            ).fetchall()
            excluded_campaigns.extend([row[0] for row in stopped_rows])
            excluded_campaigns = list(set(excluded_campaigns))
        except Exception:
            pass
"""

# Find the end of excluded_campaigns population in get_stop_optimize
# It looks like:
#         except Exception:
#             pass
# 
#         # --- Рецидивисты (уже был STOP, но трафик идёт) ---
#         repeat_offenders_ids: Set[str] = set()

# I will replace '        # --- Рецидивисты' with the addition
# Or just search for the specific place:
match = re.search(r'excluded_campaigns\.extend\(\[r\[0\] for r in excluded_rows\]\)\s+except Exception:\s+pass', content)
if match:
    content = content[:match.end()] + "\n" + addition + content[match.end():]
else:
    print("Could not find match in optimize")

with open(filepath, "w") as f:
    f.write(content)

