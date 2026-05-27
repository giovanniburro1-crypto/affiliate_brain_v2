import os
import re

FRONTEND_DIR = "/Users/andreylp/affiliate_brain/app/frontend"

OPTIONS_OLD = """<option value="3">Last 3 days</option>
                        <option value="7">Last 7 days</option>"""

OPTIONS_NEW = """<option value="3">Last 3 days</option>
                        <option value="5">Last 5 days</option>
                        <option value="7">Last 7 days</option>"""

for filename in os.listdir(FRONTEND_DIR):
    if not filename.endswith(".html"):
        continue
    filepath = os.path.join(FRONTEND_DIR, filename)
    with open(filepath, "r") as f:
        content = f.read()

    if OPTIONS_OLD in content:
        new_content = content.replace(OPTIONS_OLD, OPTIONS_NEW)
        with open(filepath, "w") as f:
            f.write(new_content)
            print(f"Updated {filename}")

