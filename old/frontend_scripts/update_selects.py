import os
import re

FRONTEND_DIR = "/Users/andreylp/affiliate_brain/app/frontend"

OPTIONS = """<option value="yesterday">Yesterday</option>
                        <option value="this_week">This week</option>
                        <option value="last_week">Last week</option>
                        <option value="2">Last 2 days</option>
                        <option value="3">Last 3 days</option>
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

    # Replace options inside any select with id containing periodSelect
    # This regex looks for <select id="periodSelect..."> ... </select>
    pattern = r'(<select\s+id="periodSelect[^"]*"(?:[^>]*)>)(.*?)(</select>)'
    
    def replacer(match):
        select_open = match.group(1)
        select_close = match.group(3)
        return f"{select_open}\n                        {OPTIONS}\n                    {select_close}"
        
    new_content = re.sub(pattern, replacer, content, flags=re.DOTALL)

    # Delete the JS functions from the HTML
    new_content = re.sub(r'function setDefaultCustomDates\(\).*?\}\n', '', new_content, flags=re.DOTALL)
    new_content = re.sub(r'function getPeriodParams\(\).*?\}\n', '', new_content, flags=re.DOTALL)
    new_content = re.sub(r'/\*\*.*?Возвращает массив дат.*?\*/\s*function getPeriodDateList\(\).*?\}\n', '', new_content, flags=re.DOTALL)
    new_content = re.sub(r'function getPeriodDateList\(\).*?\}\n', '', new_content, flags=re.DOTALL)

    # Replace any calls to getPeriodParams with buildPeriodQueryString()
    new_content = new_content.replace("getPeriodParams()", "buildPeriodQueryString()")
    
    # In re-checking.html, periodSelect has suffix
    new_content = new_content.replace("getPeriodParams(cardId)", "buildPeriodQueryString('periodSelect-' + cardId, 'customDateFrom-' + cardId, 'customDateTo-' + cardId)")
    new_content = new_content.replace("getPeriodParams(id)", "buildPeriodQueryString('periodSelect-' + id, 'customDateFrom-' + id, 'customDateTo-' + id)")

    # Replace calls to getPeriodDateList
    new_content = new_content.replace("getPeriodDateList()", "getPeriodDateListArray()")

    with open(filepath, "w") as f:
        f.write(new_content)

print("Done")
