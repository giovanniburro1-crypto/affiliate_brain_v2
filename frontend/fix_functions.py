import os
import re

FRONTEND_DIR = "/Users/andreylp/affiliate_brain/app/frontend"

def fix_file(filename, is_obj=False):
    filepath = os.path.join(FRONTEND_DIR, filename)
    if not os.path.exists(filepath):
        return
    with open(filepath, "r") as f:
        content = f.read()

    # Find the function getPeriodParams and replace its body
    if is_obj:
        new_body = """function getPeriodParams() {
            const sel = document.getElementById('periodSelect');
            const periodParamStr = buildPeriodQueryString('periodSelect', 'customDateFrom', 'customDateTo');
            let num = 14;
            if (sel.value === 'custom') {
                const from = document.getElementById('customDateFrom').value;
                const to = document.getElementById('customDateTo').value;
                if (from && to) num = Math.ceil((new Date(to) - new Date(from)) / 86400000);
            } else {
                num = parseInt(sel.value, 10) || 14;
            }
            return { periodParam: periodParamStr, periodNum: num };
        }"""
    else:
        new_body = """function getPeriodParams() {
            return buildPeriodQueryString('periodSelect', 'customDateFrom', 'customDateTo');
        }"""

    # Use regex to replace the whole function
    pattern = r'function getPeriodParams\(\)\s*\{.*?\}'
    new_content = re.sub(pattern, new_body, content, flags=re.DOTALL)
    
    if new_content != content:
        with open(filepath, "w") as f:
            f.write(new_content)
        print(f"Fixed getPeriodParams in {filename}")

# top5.html uses string
fix_file("top5.html", is_obj=False)
# bot-stop-optimize.html uses object {periodParam}
fix_file("bot-stop-optimize.html", is_obj=True)
# monetization.html uses string
fix_file("monetization.html", is_obj=False)
# index.html uses string
fix_file("index.html", is_obj=False)
# ai-top5.html uses string
fix_file("ai-top5.html", is_obj=False)

