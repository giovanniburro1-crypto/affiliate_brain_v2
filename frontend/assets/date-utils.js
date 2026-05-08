const DATE_OPTIONS = `
    <option value="yesterday">Yesterday</option>
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
    <option value="custom">Custom date</option>
`;

function getPeriodDateRange(val) {
    const today = new Date();
    let from = new Date(today);
    let to = new Date(today);

    // Helper to get X days ending yesterday
    const lastXDays = (days) => {
        const f = new Date(today);
        const t = new Date(today);
        f.setDate(today.getDate() - days);
        t.setDate(today.getDate() - 1);
        return { from: f, to: t };
    };

    switch (val) {
        case 'yesterday':
            from.setDate(today.getDate() - 1);
            to.setDate(today.getDate() - 1);
            break;
        case 'this_week':
            const day = today.getDay();
            const diff = today.getDate() - day + (day === 0 ? -6 : 1);
            from.setDate(diff);
            break;
        case 'last_week':
            const lastWeekDay = today.getDay();
            const lastWeekDiff = today.getDate() - lastWeekDay + (lastWeekDay === 0 ? -6 : 1) - 7;
            from.setDate(lastWeekDiff);
            to = new Date(from);
            to.setDate(from.getDate() + 6);
            break;
        case '2': return lastXDays(2);
        case '3': return lastXDays(3);
        case '5': return lastXDays(5);
        case '7': return lastXDays(7);
        case '14': return lastXDays(14);
        case '30': return lastXDays(30);
        case 'this_month':
            from = new Date(today.getFullYear(), today.getMonth(), 1);
            break;
        case 'last_month':
            from = new Date(today.getFullYear(), today.getMonth() - 1, 1);
            to = new Date(today.getFullYear(), today.getMonth(), 0);
            break;
        case 'this_year':
            from = new Date(today.getFullYear(), 0, 1);
            break;
        case 'last_year':
            from = new Date(today.getFullYear() - 1, 0, 1);
            to = new Date(today.getFullYear() - 1, 11, 31);
            break;
        case 'all_time':
            from = new Date(2000, 0, 1);
            break;
    }
    return { from, to };
}

function buildPeriodQueryString(selId = 'periodSelect', fromId = 'customDateFrom', toId = 'customDateTo') {
    const sel = document.getElementById(selId);
    if (!sel) return '';
    
    if (sel.value === 'custom') {
        const from = document.getElementById(fromId)?.value;
        const to = document.getElementById(toId)?.value;
        if (from && to) return 'date_from=' + encodeURIComponent(from) + '&date_to=' + encodeURIComponent(to);
    }
    
    if (sel.value === 'all_time') return 'period=0';

    const range = getPeriodDateRange(sel.value);
    
    const fromStr = range.from.getFullYear() + '-' + String(range.from.getMonth() + 1).padStart(2, '0') + '-' + String(range.from.getDate()).padStart(2, '0');
    const toStr = range.to.getFullYear() + '-' + String(range.to.getMonth() + 1).padStart(2, '0') + '-' + String(range.to.getDate()).padStart(2, '0');
    
    // We send period=14 as a fallback but date_from/date_to will take precedence
    return 'period=14&date_from=' + encodeURIComponent(fromStr) + '&date_to=' + encodeURIComponent(toStr);
}

function setDefaultCustomDates(fromId = 'customDateFrom', toId = 'customDateTo') {
    const to = new Date();
    const from = new Date(to);
    from.setDate(from.getDate() - 13);
    
    const fromInput = document.getElementById(fromId);
    const toInput = document.getElementById(toId);
    if (fromInput) fromInput.value = from.toISOString().slice(0, 10);
    if (toInput) toInput.value = to.toISOString().slice(0, 10);
}

function getPeriodDateListArray(selId = 'periodSelect') {
    const sel = document.getElementById(selId);
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
        const range = getPeriodDateRange(sel.value);
        dateFrom = range.from;
        dateTo = range.to;
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
}

// Function to replace options in all selects that match a selector
function populateDateSelects(selector = 'select[id^="periodSelect"]') {
    document.querySelectorAll(selector).forEach(sel => {
        const currentVal = sel.value;
        sel.innerHTML = DATE_OPTIONS;
        // Restore value if it exists in new options, otherwise it will default to '14'
        if (sel.querySelector(`option[value="${currentVal}"]`)) {
            sel.value = currentVal;
        }
    });
}
