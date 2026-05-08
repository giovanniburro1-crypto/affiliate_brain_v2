import os
import re

filepath = "/Users/andreylp/affiliate_brain/app/frontend/ai-company-analysis.html"
with open(filepath, "r") as f:
    content = f.read()

# Add loadDirectives
if "let directivesMap =" not in content:
    js_addition = """
        let currentAnalysisData = null;
        let directivesMap = {};
        async function loadDirectives() {
            try {
                const res = await fetch('/api/directives/by-campaigns');
                const data = await res.json();
                directivesMap = data.directives || {};
            } catch(e) { console.error('Failed to load directives', e); }
        }

        document.addEventListener('DOMContentLoaded', async () => {
            await loadDirectives();
            loadSources();
        });
"""
    content = content.replace("let currentAnalysisData = null;", js_addition.strip())

# In loadAnalysis, calculate directiveHtml
if "let directiveHtml =" not in content:
    render_addition = """
                const ACTION_COLORS = { 'STOP': 'text-red-400 bg-red-900/30 border-red-500/30', 'SCALE': 'text-green-400 bg-green-900/30 border-green-500/30', 'BUMP': 'text-purple-400 bg-purple-900/30 border-purple-500/30', 'TEST': 'text-blue-400 bg-blue-900/30 border-blue-500/30' };
                let directiveHtml = '';
                const token1 = (cid || '').split('_')[0];
                const rules = directivesMap[token1] || [];
                if (rules.length > 0) {
                    const networkRules = rules.filter(r => (r.network || '').toLowerCase() === (source || '').toLowerCase());
                    const rulesToShow = networkRules.length > 0 ? networkRules : rules;
                    directiveHtml = rulesToShow.map(r => `<span class="inline-block mt-1 px-2 py-0.5 rounded text-[10px] border ${ACTION_COLORS[r.action] || 'text-zinc-400 bg-zinc-900/30'} ml-1" title="Advertiser Directive: ${r.action} on ${r.network}">ADV: ${r.action}</span>`).join('');
                }
"""
    # Insert it before `let pathOfferLander`
    content = content.replace("let pathOfferLander = analysisData.path_offer_lander || [];", render_addition + "\n                let pathOfferLander = analysisData.path_offer_lander || [];")

    # Insert it into HTML
    content = content.replace('<div class="text-base font-bold verdict-${botProposal}">${botProposal}</div>', '<div class="text-base font-bold verdict-${botProposal}">${botProposal}</div>\n                            <div>${directiveHtml}</div>')

with open(filepath, "w") as f:
    f.write(content)

