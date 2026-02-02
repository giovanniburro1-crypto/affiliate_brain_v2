from datetime import date, timedelta, datetime
from typing import Dict, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.database import get_db
from backend.models import AIMemory

router = APIRouter()

def calc_volatility(roi_history: List[float]) -> float:
    if len(roi_history) < 2: return 50.0
    mean = sum(roi_history) / len(roi_history)
    variance = sum((x - mean) ** 2 for x in roi_history) / len(roi_history)
    return min(100, variance ** 0.5)

def calc_trend(roi_history: List[float]) -> str:
    if len(roi_history) < 4: return "UNKNOWN"
    mid = len(roi_history) // 2
    first = sum(roi_history[:mid]) / mid
    second = sum(roi_history[mid:]) / (len(roi_history) - mid)
    if second > first * 1.1: return "IMPROVING"
    elif second < first * 0.9: return "DECLINING"
    return "STABLE"

def apply_logic(metrics: Dict, roi_history: List[float]) -> Dict:
    roi, profit, spend, revenue = metrics.get('roi', 0), metrics.get('profit', 0), metrics.get('spend', 0), metrics.get('revenue', 0)
    conversions, days = metrics.get('conversions', 0), len(roi_history)
    volatility, trend = calc_volatility(roi_history), calc_trend(roi_history)
    
    verdict = "CONTINUE"
    if revenue > 0 and spend / revenue >= 3.0 and profit < 0: verdict = "STOP"
    elif roi < -20: verdict = "STOP"
    elif conversions == 0 and days >= 3 and spend > 100: verdict = "STOP"
    elif roi > 30 and volatility < 15: verdict = "SCALE"
    elif roi > 15 and volatility < 10: verdict = "SCALE"
    elif 0 < roi < 15: verdict = "OPTIMIZE"
    
    neg_streak = 0
    for r in reversed(roi_history):
        if r < 0: neg_streak += 1
        else: break
    if neg_streak >= 3: verdict = "STOP"
    
    bot_score = min(100, max(0, (roi / 50) * 40 + (30 - volatility / 100 * 30) + 30))
    confidence = min(100, max(10, days / 14 * 50 + metrics.get('clicks', 0) / 1000 * 30 - volatility / 100 * 20))
    
    reasons = {"STOP": f"❌ STOP: ROI {roi}% - убыточно", "SCALE": f"🚀 SCALE: ROI {roi}% - масштабируй!", "OPTIMIZE": f"⚙️ OPTIMIZE: ROI {roi}% - можно улучшить", "CONTINUE": f"⏸️ HOLD: ROI {roi}%"}
    
    return {"verdict": verdict, "bot_score": round(bot_score, 1), "confidence": round(confidence, 1), "reasoning": reasons.get(verdict, ""), "volatility": round(volatility, 1), "trend": trend}

@router.get("/top5")
async def get_top5(period: int = Query(7), db: Session = Depends(get_db)):
    date_from = date.today() - timedelta(days=period)
    rows = db.execute(text("SELECT campaign_id, campaign, traffic_source, SUM(cost), SUM(revenue), SUM(conversions), COUNT(*) FROM traffic_stats WHERE date >= :d AND campaign_id IS NOT NULL GROUP BY campaign_id, campaign, traffic_source HAVING SUM(cost) > 0 ORDER BY SUM(revenue)-SUM(cost) DESC LIMIT 20"), {'d': date_from}).fetchall()
    
    campaigns = []
    for row in rows:
        cid, spend, revenue = row[0], int(row[3] or 0), int(row[4] or 0)
        daily = db.execute(text("SELECT date, SUM(cost), SUM(revenue) FROM traffic_stats WHERE campaign_id = :c AND date >= :d GROUP BY date ORDER BY date"), {'c': cid, 'd': date_from}).fetchall()
        roi_history = [round((r[2]-r[1])/r[1]*100 if r[1] else 0) for r in daily]
        
        add_mon = db.execute(text("SELECT COALESCE(SUM(revenue),0) FROM additional_monetization WHERE campaign_id = :c AND date >= :d"), {'c': cid, 'd': date_from}).scalar() or 0
        revenue += int(add_mon)
        profit = revenue - spend
        roi = round((profit / spend * 100) if spend > 0 else 0)
        
        metrics = {'roi': roi, 'profit': profit, 'spend': spend, 'revenue': revenue, 'conversions': int(row[5] or 0), 'clicks': int(row[6] or 0)}
        analysis = apply_logic(metrics, roi_history)
        
        campaigns.append({"campaign_id": cid, "campaign": row[1], "source": row[2], "spend": spend, "revenue": revenue, "profit": profit, "roi": roi, "conversions": metrics['conversions'], "clicks": metrics['clicks'], **analysis})
    
    campaigns.sort(key=lambda x: x['bot_score'], reverse=True)
    summary = {"total_profit": sum(c['profit'] for c in campaigns), "scale_count": len([c for c in campaigns if c['verdict'] == 'SCALE']), "stop_count": len([c for c in campaigns if c['verdict'] == 'STOP'])}
    
    return {"campaigns": campaigns[:5], "all_campaigns": campaigns, "summary": summary}

@router.post("/analyze")
async def analyze(campaign_id: str = Query(...), period: int = Query(7), db: Session = Depends(get_db)):
    date_from = date.today() - timedelta(days=period)
    row = db.execute(text("SELECT campaign, traffic_source, SUM(cost), SUM(revenue), SUM(conversions), COUNT(*) FROM traffic_stats WHERE campaign_id = :c AND date >= :d GROUP BY campaign, traffic_source"), {'c': campaign_id, 'd': date_from}).fetchone()
    if not row: return {"error": "Not found"}
    
    spend, revenue = int(row[2] or 0), int(row[3] or 0)
    daily = db.execute(text("SELECT date, SUM(cost), SUM(revenue) FROM traffic_stats WHERE campaign_id = :c AND date >= :d GROUP BY date ORDER BY date"), {'c': campaign_id, 'd': date_from}).fetchall()
    roi_history = [round((r[2]-r[1])/r[1]*100 if r[1] else 0) for r in daily]
    
    profit = revenue - spend
    roi = round((profit / spend * 100) if spend > 0 else 0)
    metrics = {'roi': roi, 'profit': profit, 'spend': spend, 'revenue': revenue, 'conversions': int(row[4] or 0), 'clicks': int(row[5] or 0)}
    analysis = apply_logic(metrics, roi_history)
    
    try:
        db.add(AIMemory(campaign_id=campaign_id, decision_date=datetime.now(), bot_verdict=analysis['verdict'], bot_score=analysis['bot_score'], bot_confidence=analysis['confidence'], bot_reasoning=analysis['reasoning']))
        db.commit()
    except: db.rollback()
    
    return {"campaign_id": campaign_id, "campaign": row[0], "source": row[1], **metrics, **analysis}
