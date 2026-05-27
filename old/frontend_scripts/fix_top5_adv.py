import os
import re

filepath = "/Users/andreylp/affiliate_brain/app/frontend/top5.html"
with open(filepath, "r") as f:
    content = f.read()

# Add loadDirectives
if "loadDirectives" not in content:
    js_addition = """
        let directivesMap = {};
        async function loadDirectives() {
            try {
                const res = await fetch('/api/directives/by-campaigns');
                const data = await res.json();
                directivesMap = data.directives || {};
            } catch(e) { console.error('Failed to load directives', e); }
        }

        document.addEventListener('DOMContentLoaded', async () => { lucide.createIcons(); setDefaultCustomDates(); toggleCustomDate(); await loadDirectives(); loadTop5(); });
"""
    # Replace DOMContentLoaded line
    content = re.sub(r"document\.addEventListener\('DOMContentLoaded',\s*\(\)\s*=>\s*\{\s*lucide\.createIcons\(\);\s*setDefaultCustomDates\(\);\s*toggleCustomDate\(\);\s*loadTop5\(\);\s*\}\);", js_addition.strip(), content)

# Add directive badge generation in render
if "directiveHtml" not in content:
    render_addition = """
                const ACTION_COLORS = { 'STOP': 'text-red-400 bg-red-900/30 border-red-500/30', 'SCALE': 'text-green-400 bg-green-900/30 border-green-500/30', 'BUMP': 'text-purple-400 bg-purple-900/30 border-purple-500/30', 'TEST': 'text-blue-400 bg-blue-900/30 border-blue-500/30' };
                let directiveHtml = '';
                const token1 = (c.campaign_id || '').split('_')[0];
                const rules = directivesMap[token1] || [];
                if (rules.length > 0) {
                    const networkRules = rules.filter(r => (r.network || '').toLowerCase() === (c.source || '').toLowerCase());
                    const rulesToShow = networkRules.length > 0 ? networkRules : rules;
                    directiveHtml = rulesToShow.map(r => `<span class="px-2 py-0.5 rounded text-xs border ${ACTION_COLORS[r.action] || 'text-zinc-400 bg-zinc-900/30'} ml-2" title="Advertiser Directive: ${r.action} on ${r.network}">ADV: ${r.action}</span>`).join('');
                }
"""
    # In top5.html, data.campaigns.map((c, i) => ` is the start
    content = content.replace("document.getElementById('top5Cards').innerHTML = data.campaigns.map((c, i) => `", "document.getElementById('top5Cards').innerHTML = data.campaigns.map((c, i) => {\n" + render_addition + "\nreturn `")
    
    # We also need to change the end of the map from `).join(''); to `}).join('');
    content = content.replace("`).join('');", "`}).join('');")

    # Insert directiveHtml after verdict
    content = content.replace('<span class="verdict-${c.verdict} px-2 py-0.5 rounded text-xs">${c.verdict}</span>', '<span class="verdict-${c.verdict} px-2 py-0.5 rounded text-xs">${c.verdict}</span>${directiveHtml}')

with open(filepath, "w") as f:
    f.write(content)

