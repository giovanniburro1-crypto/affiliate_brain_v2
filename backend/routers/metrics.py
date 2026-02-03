from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.database import get_db

router = APIRouter()

@router.get("/metrics/summary")
async def get_summary(period: int = Query(7), source: Optional[str] = None, db: Session = Depends(get_db)):
    date_from = date.today() - timedelta(days=period)
    source_filter = "AND traffic_source = :source" if source and source != 'all' else ""
    query = text(f"SELECT COALESCE(SUM(cost),0), COALESCE(SUM(revenue),0), COALESCE(SUM(conversions),0), COUNT(*) FROM traffic_stats WHERE date >= :date_from {source_filter}")
    params = {'date_from': date_from}
    if source and source != 'all': params['source'] = source
    r = db.execute(query, params).fetchone()
    spend, revenue, conversions, clicks = int(r[0]), int(r[1]), int(r[2]), int(r[3])
    add_mon = db.execute(text("SELECT COALESCE(SUM(revenue),0) FROM additional_monetization WHERE date >= :d"), {'d': date_from}).scalar() or 0
    total_revenue = revenue + int(add_mon)
    profit = total_revenue - spend
    roi = round((profit / spend * 100) if spend > 0 else 0)
    return {"spend": spend, "revenue": total_revenue, "profit": profit, "roi": roi, "conversions": conversions, "clicks": clicks}

@router.get("/metrics/campaigns")
async def get_campaigns(period: int = Query(7), source: Optional[str] = None, db: Session = Depends(get_db)):
    date_from = date.today() - timedelta(days=period)
    source_filter = "AND traffic_source = :source" if source and source != 'all' else ""
    query = text(f"SELECT campaign_id, campaign, traffic_source, SUM(cost), SUM(revenue), SUM(conversions), COUNT(*) FROM traffic_stats WHERE date >= :date_from {source_filter} GROUP BY campaign_id, campaign, traffic_source ORDER BY SUM(revenue)-SUM(cost) DESC LIMIT 50")
    params = {'date_from': date_from}
    if source and source != 'all': params['source'] = source
    rows = db.execute(query, params).fetchall()
    campaigns = []
    for row in rows:
        spend, revenue = int(row[3] or 0), int(row[4] or 0)
        profit = revenue - spend
        roi = round((profit / spend * 100) if spend > 0 else 0)
        campaigns.append({"campaign_id": row[0], "campaign": row[1], "source": row[2], "spend": spend, "revenue": revenue, "profit": profit, "roi": roi, "conversions": int(row[5] or 0), "clicks": int(row[6] or 0)})
    return {"campaigns": campaigns}

@router.get("/metrics/sources")
async def get_sources(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT DISTINCT traffic_source FROM traffic_stats WHERE traffic_source IS NOT NULL ORDER BY traffic_source")).fetchall()
    return {"sources": [r[0] for r in result]}

@router.get("/metrics/daily")
async def get_daily(period: int = Query(14), db: Session = Depends(get_db)):
    date_from = date.today() - timedelta(days=period)
    rows = db.execute(text("SELECT date, SUM(cost), SUM(revenue), SUM(conversions) FROM traffic_stats WHERE date >= :d GROUP BY date ORDER BY date"), {'d': date_from}).fetchall()
    daily = []
    for row in rows:
        cost, revenue = int(row[1] or 0), int(row[2] or 0)
        daily.append({"date": row[0].isoformat(), "cost": cost, "revenue": revenue, "profit": revenue - cost, "conversions": int(row[3] or 0)})
    return {"daily": daily}

@router.get("/metrics/sources-table")
async def get_sources_table(period: int = Query(14), db: Session = Depends(get_db)):
    date_from = date.today() - timedelta(days=period)
    sources = db.execute(text("SELECT DISTINCT traffic_source FROM traffic_stats WHERE date >= :d AND traffic_source IS NOT NULL"), {'d': date_from}).fetchall()
    result = []
    for (src,) in sources:
        daily = db.execute(text("SELECT date, SUM(cost), SUM(revenue) FROM traffic_stats WHERE traffic_source = :s AND date >= :d GROUP BY date ORDER BY date"), {'s': src, 'd': date_from}).fetchall()
        days = {}
        total_cost, total_revenue = 0, 0
        for row in daily:
            cost, revenue = int(row[1] or 0), int(row[2] or 0)
            profit = revenue - cost
            color = "green" if cost > 0 and (profit/cost*100) > 10 else "red" if cost > 0 and (profit/cost*100) < -10 else "yellow"
            days[row[0].isoformat()] = {"profit": profit, "color": color}
            total_cost += cost
            total_revenue += revenue
        total_profit = total_revenue - total_cost
        roi = round((total_profit / total_cost * 100) if total_cost > 0 else 0)
        result.append({"source": src, "total_cost": total_cost, "total_revenue": total_revenue, "total_profit": total_profit, "roi": roi, "days": days})
    result.sort(key=lambda x: x['total_profit'], reverse=True)
    return {"sources": result, "date_from": date_from.isoformat(), "date_to": date.today().isoformat()}

@router.get("/metrics/splits")
async def get_splits(period: int = Query(14), db: Session = Depends(get_db)):
    date_from = date.today() - timedelta(days=period)
    
    os_data = db.execute(text("SELECT os, COUNT(*), SUM(cost), SUM(revenue) FROM traffic_stats WHERE date >= :d AND os IS NOT NULL GROUP BY os ORDER BY COUNT(*) DESC LIMIT 6"), {'d': date_from}).fetchall()
    device_data = db.execute(text("SELECT device_type, COUNT(*), SUM(cost), SUM(revenue) FROM traffic_stats WHERE date >= :d AND device_type IS NOT NULL GROUP BY device_type ORDER BY COUNT(*) DESC"), {'d': date_from}).fetchall()
    
    os_result = []
    for row in os_data:
        spend, revenue = int(row[2] or 0), int(row[3] or 0)
        os_result.append({"name": row[0], "clicks": int(row[1]), "spend": spend, "revenue": revenue, "profit": revenue - spend})
    
    device_result = []
    for row in device_data:
        spend, revenue = int(row[2] or 0), int(row[3] or 0)
        device_result.append({"name": row[0], "clicks": int(row[1]), "spend": spend, "revenue": revenue, "profit": revenue - spend})
    
    return {"os": os_result, "device": device_result}

@router.get("/orphans")
async def get_orphans(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT id, token1, date, revenue, source FROM orphans ORDER BY revenue DESC LIMIT 100")).fetchall()
    orphans = [{"id": row[0], "token1": row[1], "date": row[2].isoformat() if row[2] else None, "revenue": float(row[3] or 0), "source": row[4]} for row in rows]
    total = db.execute(text("SELECT COUNT(*), SUM(revenue) FROM orphans")).fetchone()
    return {"orphans": orphans, "total_count": total[0] or 0, "total_revenue": float(total[1] or 0)}

@router.post("/orphans/match")
async def match_orphan(orphan_id: int, campaign_id: str, db: Session = Depends(get_db)):
    orphan = db.execute(text("SELECT token1, date, revenue, source FROM orphans WHERE id = :id"), {"id": orphan_id}).fetchone()
    if not orphan:
        return {"success": False, "error": "Orphan not found"}
    db.execute(text("INSERT INTO additional_monetization (campaign_id, token1, date, revenue, source) VALUES (:cid, :t, :d, :r, :s)"), {"cid": campaign_id, "t": orphan[0], "d": orphan[1], "r": orphan[2], "s": orphan[3]})
    db.execute(text("DELETE FROM orphans WHERE id = :id"), {"id": orphan_id})
    db.commit()
    return {"success": True}
