import os

FRONTEND_DIR = "/Users/andreylp/affiliate_brain/app/frontend"

OPTIONS_OLD = """<option value="7">7 days</option>
                        <option value="14" selected>14 days</option>
                        <option value="30">30 days</option>"""

OPTIONS_NEW = """<option value="yesterday">Yesterday</option>
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
                        <option value="all_time">All time</option>"""

def replace_in_file(filepath):
    with open(filepath, "r") as f:
        content = f.read()

    # Add <script src="/assets/date-utils.js"></script> to head
    if '<script src="/assets/date-utils.js"></script>' not in content:
        content = content.replace(
            '<link rel="stylesheet" href="/assets/theme.css">',
            '<link rel="stylesheet" href="/assets/theme.css">\n    <script src="/assets/date-utils.js"></script>'
        )

    # Replace options
    content = content.replace(OPTIONS_OLD, OPTIONS_NEW)

    # index.html, monetization.html, top5.html, ai-top5.html have getPeriodParams returning string
    # Let's replace the whole getPeriodParams block if it matches the string return type
    GET_PARAMS_STR = """        function getPeriodParams() {
            const sel = document.getElementById('periodSelect');
            if (sel.value === 'custom') {
                const from = document.getElementById('customDateFrom').value;
                const to = document.getElementById('customDateTo').value;
                if (from && to) return 'date_from=' + encodeURIComponent(from) + '&date_to=' + encodeURIComponent(to);
            }
            return 'period=' + sel.value;
        }"""
    
    GET_PARAMS_NEW_STR = """        function getPeriodParams() {
            return buildPeriodQueryString('periodSelect', 'customDateFrom', 'customDateTo');
        }"""
    
    content = content.replace(GET_PARAMS_STR, GET_PARAMS_NEW_STR)

    # bot-top5.html has a different getPeriodParams
    GET_PARAMS_OBJ = """        function getPeriodParams() {
            const sel = document.getElementById('periodSelect');
            if (sel.value === 'custom') {
                const from = document.getElementById('customDateFrom').value;
                const to = document.getElementById('customDateTo').value;
                if (from && to) return { periodParam: 'date_from=' + encodeURIComponent(from) + '&date_to=' + encodeURIComponent(to), periodNum: Math.ceil((new Date(to) - new Date(from)) / 86400000) };
            }
            return { periodParam: 'period=' + sel.value, periodNum: parseInt(sel.value, 10) };
        }"""
    GET_PARAMS_NEW_OBJ = """        function getPeriodParams() {
            const sel = document.getElementById('periodSelect');
            if (sel.value === 'custom') {
                const from = document.getElementById('customDateFrom').value;
                const to = document.getElementById('customDateTo').value;
                if (from && to) return { periodParam: 'date_from=' + encodeURIComponent(from) + '&date_to=' + encodeURIComponent(to), periodNum: Math.ceil((new Date(to) - new Date(from)) / 86400000) };
            }
            const periodParamStr = buildPeriodQueryString('periodSelect', 'customDateFrom', 'customDateTo');
            const num = parseInt(sel.value, 10) || 14; // fallback for non-ints if used
            return { periodParam: periodParamStr, periodNum: num };
        }"""
    content = content.replace(GET_PARAMS_OBJ, GET_PARAMS_NEW_OBJ)

    # getPeriodDateList in index.html, monetization.html
    GET_LIST_OLD = """        function getPeriodDateList() {
            const sel = document.getElementById('periodSelect');
            let dateFrom, dateTo;
            if (sel.value === 'custom') {
                const fromStr = document.getElementById('customDateFrom').value;
                const toStr = document.getElementById('customDateTo').value;
                if (!fromStr || !toStr) {
                    const today = new Date();
                    dateTo = today;
                    dateFrom = new Date(today);
                    dateFrom.setDate(dateFrom.getDate() - 13);
                } else {
                    dateFrom = new Date(fromStr);
                    dateTo = new Date(toStr);
                }
            } else {
                const days = parseInt(sel.value, 10) || 14;
                dateTo = new Date();
                dateFrom = new Date(dateTo);
                dateFrom.setDate(dateFrom.getDate() - (days - 1));
            }
            const list = [];
            const cur = new Date(dateFrom);
            while (cur <= dateTo) {
                const m = String(cur.getMonth() + 1).padStart(2, '0');
                const d = String(cur.getDate()).padStart(2, '0');
                list.push(m + '-' + d);
                cur.setDate(cur.getDate() + 1);
            }
            return list;
        }"""
    GET_LIST_NEW = """        function getPeriodDateList() {
            return getPeriodDateListArray('periodSelect');
        }"""
    content = content.replace(GET_LIST_OLD, GET_LIST_NEW)

    # re-checking.html
    RECHECK_OLD = """        function getPeriodParamsForCard(cardId) {
            const sel = document.getElementById('periodSelect-' + cardId);
            if (!sel) return { periodParam: 'period=7', period: 7 };
            if (sel.value === 'custom') {
                const from = document.getElementById('customDateFrom-' + cardId)?.value;
                const to = document.getElementById('customDateTo-' + cardId)?.value;
                if (from && to) return { periodParam: 'date_from=' + encodeURIComponent(from) + '&date_to=' + encodeURIComponent(to), period: null, date_from: from, date_to: to };
            }
            const period = parseInt(sel.value, 10) || 7;
            return { periodParam: 'period=' + period, period: period };
        }"""
    RECHECK_NEW = """        function getPeriodParamsForCard(cardId) {
            const sel = document.getElementById('periodSelect-' + cardId);
            if (!sel) return { periodParam: 'period=7', period: 7 };
            if (sel.value === 'custom') {
                const from = document.getElementById('customDateFrom-' + cardId)?.value;
                const to = document.getElementById('customDateTo-' + cardId)?.value;
                if (from && to) return { periodParam: 'date_from=' + encodeURIComponent(from) + '&date_to=' + encodeURIComponent(to), period: null, date_from: from, date_to: to };
            }
            if (sel.value === 'all_time') return { periodParam: 'period=0', period: 0 };
            const range = getPeriodDateRange(sel.value);
            const fromStr = range.from.toISOString().slice(0, 10);
            const toStr = range.to.toISOString().slice(0, 10);
            return { periodParam: 'date_from=' + encodeURIComponent(fromStr) + '&date_to=' + encodeURIComponent(toStr), period: null, date_from: fromStr, date_to: toStr };
        }"""
    content = content.replace(RECHECK_OLD, RECHECK_NEW)

    with open(filepath, "w") as f:
        f.write(content)

for filename in ["index.html", "monetization.html", "top5.html", "bot-top5.html", "re-checking.html", "ai-top5.html", "bot-stop-optimize.html"]:
    replace_in_file(os.path.join(FRONTEND_DIR, filename))

print("Done")
