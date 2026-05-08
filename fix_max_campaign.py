import re

# Fix metrics.py
f = "/Users/andreylp/affiliate_brain/app/backend/routers/metrics.py"
with open(f, "r") as file:
    content = file.read()

# 1. line 194
content = content.replace(
    "SELECT campaign_id, MAX(campaign) as campaign,",
    "SELECT campaign_id, MAX(COALESCE(date, '') || '|||' || campaign) as campaign,"
)
content = content.replace(
    "name = row[1].replace('Mediabuys - ', '') if row[1] else row[0]",
    "name_raw = row[1]\n            name_clean = name_raw.split('|||', 1)[1] if name_raw and '|||' in name_raw else name_raw\n            name = name_clean.replace('Mediabuys - ', '') if name_clean else row[0]"
)

# 2. line 336
content = content.replace(
    "SELECT campaign_id, MAX(campaign), traffic_source,",
    "SELECT campaign_id, MAX(COALESCE(date, '') || '|||' || campaign), traffic_source,"
)
content = content.replace(
    "campaign_name = row[1].replace('Mediabuys - ', '') if row[1] else row[0]",
    "name_raw = row[1]\n        c_name = name_raw.split('|||', 1)[1] if name_raw and '|||' in name_raw else name_raw\n        campaign_name = c_name.replace('Mediabuys - ', '') if c_name else row[0]"
)

# 3. line 1044
content = content.replace(
    "MAX(ts.campaign) as name,",
    "MAX(COALESCE(ts.date, '') || '|||' || ts.campaign) as name,"
)
content = content.replace(
    "camp_name = row[2].replace('Mediabuys - ', '') if row[2] else ''",
    "name_raw = row[2]\n        c_name = name_raw.split('|||', 1)[1] if name_raw and '|||' in name_raw else name_raw\n        camp_name = c_name.replace('Mediabuys - ', '') if c_name else ''"
)

with open(f, "w") as file:
    file.write(content)

# Fix top5_service_v2_complete.py
f = "/Users/andreylp/affiliate_brain/app/backend/services/top5_service_v2_complete.py"
with open(f, "r") as file:
    content = file.read()

content = content.replace(
    "SELECT campaign_id, MAX(campaign), MAX(traffic_source),",
    "SELECT campaign_id, MAX(COALESCE(date, '') || '|||' || campaign), MAX(traffic_source),"
)
content = content.replace(
    '"campaign": r[1] or cid,',
    '"campaign": (r[1].split("|||", 1)[1] if r[1] and "|||" in r[1] else r[1]) or cid,'
)
content = content.replace(
    '"campaign": r[1] or c_id,',
    '"campaign": (r[1].split("|||", 1)[1] if r[1] and "|||" in r[1] else r[1]) or c_id,'
)

with open(f, "w") as file:
    file.write(content)

