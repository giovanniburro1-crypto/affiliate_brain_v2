import os
import re

FRONTEND_DIR = "/Users/andreylp/affiliate_brain/app/frontend"

NEW_OPTIONS = """                        <option value="yesterday">Yesterday</option>
                        <option value="this_week">This week</option>
                        <option value="last_week">Last week</option>
                        <option value="2">Last 2 days</option>
                        <option value="3">Last 3 days</option>
                        <option value="5">Last 5 days</option>
                        <option value="7">Last 7 days</option>
                        <option value="14" selected>Last 14 days</option>
                        <option value="30">Last 30 days</option>
                        <option value="this_month">This month</option>
                        <option value="last_month">Last month</option>
                        <option value="this_year">This year</option>
                        <option value="last_year">Last year</option>
                        <option value="all_time">All time</option>
                        <option value="custom">Custom date</option>"""

for filename in os.listdir(FRONTEND_DIR):
    if not filename.endswith(".html"):
        continue
    filepath = os.path.join(FRONTEND_DIR, filename)
    with open(filepath, "r") as f:
        content = f.read()

    # Regex to find <select id="periodSelect"...> ... </select>
    pattern = r'(<select\s+id="periodSelect[^"]*"(?:[^>]*)>)(.*?)(</select>)'
    
    def replacer(match):
        select_open = match.group(1)
        select_close = match.group(3)
        return f"{select_open}\n{NEW_OPTIONS}\n                    {select_close}"
        
    if "periodSelect" in content:
        new_content = re.sub(pattern, replacer, content, flags=re.DOTALL)
        if new_content != content:
            with open(filepath, "w") as f:
                f.write(new_content)
            print(f"Updated options in {filename}")

