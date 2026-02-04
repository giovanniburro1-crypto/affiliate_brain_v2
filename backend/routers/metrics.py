from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.database import get_db

router = APIRouter()


def _get_totals(db: Session, date_from: date, source: Optional[str]):
    """Единый расчёт тоталов: spend, base_revenue, add_mon, total_profit. Без AS в SELECT — порядок колонок: 0=cost, 1=revenue, 2=conversions, 3=clicks."""
    source_filter = "AND traffic_source = :source" if source and source != 'all' else ""
    params = {'date_from': date_from}
    if source and source != 'all':
        params['source'] = source
    r = db.execute(text(
        f"SELECT COALESCE(SUM(cost),0), COALESCE(SUM(revenue),0), COALESCE(SUM(conversions),0), COUNT(*) "
        f"FROM traffic_stats WHERE date >= :date_from {source_filter}"
    ), params).fetchone()
    total_spend = int(round(float(r[0] or 0)))
    total_base_revenue = int(round(float(r[1] or 0)))
    conversions = int(r[2] or 0)
    clicks = int(r[3] or 0)

    if source and source != 'all':
        add_mon = db.execute(text("""
            SELECT COALESCE(SUM(am.revenue), 0)
            FROM additional_monetization am
            WHERE am.date >= :date_from
              AND am.campaign_id IN (SELECT DISTINCT campaign_id FROM traffic_stats WHERE traffic_source = :source)
        """), params).scalar() or 0
    else:
        add_mon = db.execute(text(
            "SELECT COALESCE(SUM(revenue),0) FROM additional_monetization WHERE date >= :date_from"
        ), {'date_from': date_from}).scalar() or 0

    add_mon = int(round(float(add_mon or 0)))
    total_profit = total_base_revenue + add_mon - total_spend
    return total_spend, total_base_revenue, add_mon, total_profit, conversions, clicks


@router.get("/metrics/summary")
async def get_summary(period: int = Query(7), source: Optional[str] = None, db: Session = Depends(get_db)):
    date_from = date.today() - timedelta(days=period)
    total_spend, total_base_revenue, add_mon, profit, conversions, clicks = _get_totals(db, date_from, source)
    total_revenue = total_base_revenue + add_mon
    roi = round((profit / total_spend * 100) if total_spend > 0 else 0)
    return {"spend": total_spend, "revenue": total_revenue, "profit": profit, "roi": roi, "conversions": conversions, "clicks": clicks}

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
async def get_splits(period: int = Query(14), source: Optional[str] = None, db: Session = Depends(get_db)):
    date_from = date.today() - timedelta(days=period)
    total_spend, total_base_revenue, add_mon, total_profit, _, _ = _get_totals(db, date_from, source)

    source_filter = "AND traffic_source = :source" if source and source != 'all' else ""
    params = {'date_from': date_from}
    if source and source != 'all':
        params['source'] = source

    # OS: один запрос, читаем по именам колонок (cost_sum, revenue_sum), чтобы не зависеть от порядка
    os_raw = db.execute(text(f"""
        SELECT COALESCE(os, 'Unknown'), COUNT(*), SUM(cost), SUM(revenue)
        FROM traffic_stats WHERE date >= :date_from {source_filter}
        GROUP BY COALESCE(os, 'Unknown')
    """), params).fetchall()

    total_os_clicks = sum(int(row[1] or 0) for row in os_raw)
    os_base_revenue_sum = sum(int(round(float(row[3] or 0))) for row in os_raw)
    if os_base_revenue_sum == 0:
        os_base_revenue_sum = 1

    os_groups = {"iOS": {"clicks": 0, "profit": 0}, "Android": {"clicks": 0, "profit": 0}, "Other": {"clicks": 0, "profit": 0}, "Unknown": {"clicks": 0, "profit": 0}}
    for row in os_raw:
        os_name = (str(row[0] or 'Unknown')).strip() or 'Unknown'
        clicks = int(row[1] or 0)
        cost_os = int(round(float(row[2] or 0)))
        revenue_os = int(round(float(row[3] or 0)))
        profit_base_os = revenue_os - cost_os
        revenue_share = revenue_os / os_base_revenue_sum
        add_mon_os = round(add_mon * revenue_share)
        profit_os = profit_base_os + add_mon_os

        if os_name == "iOS":
            os_groups["iOS"]["clicks"] += clicks
            os_groups["iOS"]["profit"] += profit_os
        elif os_name == "Android":
            os_groups["Android"]["clicks"] += clicks
            os_groups["Android"]["profit"] += profit_os
        elif os_name == "Unknown":
            os_groups["Unknown"]["clicks"] += clicks
            os_groups["Unknown"]["profit"] += profit_os
        else:
            os_groups["Other"]["clicks"] += clicks
            os_groups["Other"]["profit"] += profit_os

    os_result = []
    for name in ["iOS", "Android", "Other", "Unknown"]:
        data = os_groups[name]
        traffic_pct = round(data["clicks"] / total_os_clicks * 100) if total_os_clicks > 0 else 0
        profit_pct = round(data["profit"] / total_profit * 100) if total_profit != 0 else 0
        profit_pct = max(-9999, min(9999, profit_pct))
        os_result.append({"name": name, "clicks": data["clicks"], "traffic_pct": traffic_pct, "profit": data["profit"], "profit_pct": profit_pct})

    # Device: порядок колонок 0=device_name, 1=clicks, 2=cost_sum, 3=revenue_sum — читаем по индексу
    device_raw = db.execute(text(f"""
        SELECT COALESCE(device_type, 'Unknown'), COUNT(*), SUM(cost), SUM(revenue)
        FROM traffic_stats WHERE date >= :date_from {source_filter}
        GROUP BY COALESCE(device_type, 'Unknown')
    """), params).fetchall()

    total_dev_clicks = sum(int(row[1] or 0) for row in device_raw)
    dev_base_revenue_sum = sum(int(round(float(row[3] or 0))) for row in device_raw)
    if dev_base_revenue_sum == 0:
        dev_base_revenue_sum = 1

    device_groups = {"Mobile": {"clicks": 0, "profit": 0}, "Desktop": {"clicks": 0, "profit": 0}, "Other": {"clicks": 0, "profit": 0}, "Unknown": {"clicks": 0, "profit": 0}}
    for row in device_raw:
        dev_name = (str(row[0] or 'Unknown')).strip() or 'Unknown'
        clicks = int(row[1] or 0)
        cost_dev = int(round(float(row[2] or 0)))
        revenue_dev = int(round(float(row[3] or 0)))
        profit_base_dev = revenue_dev - cost_dev
        revenue_share = revenue_dev / dev_base_revenue_sum
        add_mon_dev = round(add_mon * revenue_share)
        profit_dev = profit_base_dev + add_mon_dev

        if dev_name == "Mobile":
            device_groups["Mobile"]["clicks"] += clicks
            device_groups["Mobile"]["profit"] += profit_dev
        elif dev_name == "Desktop":
            device_groups["Desktop"]["clicks"] += clicks
            device_groups["Desktop"]["profit"] += profit_dev
        elif dev_name == "Unknown":
            device_groups["Unknown"]["clicks"] += clicks
            device_groups["Unknown"]["profit"] += profit_dev
        else:
            device_groups["Other"]["clicks"] += clicks
            device_groups["Other"]["profit"] += profit_dev

    device_result = []
    for name in ["Mobile", "Desktop", "Other", "Unknown"]:
        data = device_groups[name]
        traffic_pct = round(data["clicks"] / total_dev_clicks * 100) if total_dev_clicks > 0 else 0
        profit_pct = round(data["profit"] / total_profit * 100) if total_profit != 0 else 0
        profit_pct = max(-9999, min(9999, profit_pct))
        device_result.append({"name": name, "clicks": data["clicks"], "traffic_pct": traffic_pct, "profit": data["profit"], "profit_pct": profit_pct})

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

@router.get("/metrics/traffic-sources-summary")
async def get_traffic_sources_summary(period: int = Query(14), db: Session = Depends(get_db)):
    date_from = date.today() - timedelta(days=period)
    
    # Получаем данные по traffic sources (traffic_stats + additional_monetization)
    sources = db.execute(text("""
        SELECT 
            ts.traffic_source,
            SUM(ts.cost) as spend,
            SUM(ts.revenue) as base_revenue
        FROM traffic_stats ts
        WHERE ts.date >= :d AND ts.traffic_source IS NOT NULL AND ts.traffic_source != 'AddMonetisation'
        GROUP BY ts.traffic_source
    """), {'d': date_from}).fetchall()
    
    result = []
    for row in sources:
        source_name = row[0]
        spend = int(row[1] or 0)
        base_revenue = int(row[2] or 0)
        
        # Добавляем additional_monetization для кампаний этого source
        add_revenue = db.execute(text("""
            SELECT COALESCE(SUM(am.revenue), 0)
            FROM additional_monetization am
            JOIN traffic_stats ts ON am.campaign_id = ts.campaign_id
            WHERE ts.traffic_source = :src AND am.date >= :d
        """), {'src': source_name, 'd': date_from}).scalar() or 0
        
        total_revenue = base_revenue + int(add_revenue)
        profit = total_revenue - spend
        roi = round((profit / spend * 100) if spend > 0 else 0)
        
        result.append({
            "source": source_name,
            "spend": spend,
            "revenue": total_revenue,
            "profit": profit,
            "roi": roi
        })
    
    result.sort(key=lambda x: x['profit'], reverse=True)
    return {"sources": result}

@router.get("/metrics/campaigns-table")
async def get_campaigns_table(period: int = Query(14), db: Session = Depends(get_db)):
    date_from = date.today() - timedelta(days=period)
    
    # Получаем топ-25 кампаний по spend
    campaigns = db.execute(text("""
        SELECT campaign_id, campaign, SUM(cost) as total_spend
        FROM traffic_stats 
        WHERE date >= :d AND campaign_id IS NOT NULL
        GROUP BY campaign_id, campaign
        ORDER BY total_spend DESC
        LIMIT 25
    """), {'d': date_from}).fetchall()
    
    result = []
    for row in campaigns:
        campaign_id = row[0]
        campaign_name = row[1]
        total_spend = int(row[2] or 0)
        
        # Получаем данные по дням для этой кампании
        daily = db.execute(text("""
            SELECT date, SUM(cost), SUM(revenue)
            FROM traffic_stats 
            WHERE campaign_id = :cid AND date >= :d
            GROUP BY date
            ORDER BY date
        """), {'cid': campaign_id, 'd': date_from}).fetchall()
        
        days = {}
        for day_row in daily:
            day_date = day_row[0].strftime('%m-%d')
            day_spend = int(day_row[1] or 0)
            day_base_revenue = int(day_row[2] or 0)
            
            # Добавляем additional_monetization для этой кампании в этот день
            day_add_revenue = db.execute(text("""
                SELECT COALESCE(SUM(revenue), 0)
                FROM additional_monetization
                WHERE campaign_id = :cid AND date = :dt
            """), {'cid': campaign_id, 'dt': day_row[0]}).scalar() or 0
            
            day_total_revenue = day_base_revenue + int(day_add_revenue)
            day_profit = day_total_revenue - day_spend
            
            # Определяем цвет (profit%)
            day_profit_pct = (day_profit / day_spend * 100) if day_spend > 0 else 0
            if day_profit_pct < -10:
                color = 'red'
            elif day_profit_pct > 10:
                color = 'green'
            else:
                color = 'none'
            
            days[day_date] = {'profit': day_profit, 'color': color}
        
        result.append({
            'token1': campaign_id,
            'campaign': campaign_name,
            'spend': total_spend,
            'days': days
        })
    
    return {'campaigns': result, 'date_from': date_from.strftime('%Y-%m-%d')}
