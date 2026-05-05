from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.database import get_db

router = APIRouter()

# Исключаем из трафика источники с доп. монетизацией (не только 'AddMonetisation', но и любые со словом monetisation)
FILTER_OUT_MONETISATION = "AND traffic_source != 'AddMonetisation' AND LOWER(traffic_source) NOT LIKE '%monetisation%'"


def _apply_source_filter(params: dict, source: Optional[str], default_filter: str = "") -> str:
    """Хелпер для применения фильтра по источнику (поддерживает мультивыбор через запятую)."""
    if not source or source == "all":
        return default_filter
    
    sources = [s.strip() for s in source.split(',') if s.strip()]
    if not sources:
        return default_filter
    
    if len(sources) == 1:
        params['source'] = sources[0]
        return "AND traffic_source = :source"
    else:
        placeholders = []
        for i, s in enumerate(sources):
            p_name = f"src_{i}"
            params[p_name] = s
            placeholders.append(f":{p_name}")
        return f"AND traffic_source IN ({', '.join(placeholders)})"


def _period_or_range(period: int, date_from_str: Optional[str], date_to_str: Optional[str]) -> tuple:
    """Возвращает (date_from, date_to). Если переданы date_from_str и date_to_str — парсим их, иначе период от сегодня."""
    today = date.today()
    if date_from_str and date_to_str:
        try:
            d_from = date.fromisoformat(date_from_str.strip()[:10])
            d_to = date.fromisoformat(date_to_str.strip()[:10])
            if d_from <= d_to:
                return (d_from, d_to)
        except (ValueError, TypeError):
            pass
    return (today - timedelta(days=period), today)


def _get_totals(db: Session, date_from: date, date_to: date, source: Optional[str]):
    """Единый расчёт тоталов: spend, base_revenue, add_mon, total_profit."""
    params = {'date_from': date_from, 'date_to': date_to}
    source_filter = _apply_source_filter(params, source, FILTER_OUT_MONETISATION)
    
    r = db.execute(text(
        f"SELECT COALESCE(SUM(cost),0), COALESCE(SUM(revenue),0), COALESCE(SUM(conversions),0), COUNT(*) "
        f"FROM traffic_stats WHERE date >= :date_from AND date <= :date_to AND traffic_source IS NOT NULL {source_filter}"
    ), params).fetchone()
    
    total_spend = int(round(float(r[0] or 0)))
    total_base_revenue = int(round(float(r[1] or 0)))
    conversions = int(r[2] or 0)
    clicks = int(r[3] or 0)

    # Для доп. монетизации фильтруем по кампаниям, которые были активны в выбранных источниках
    if source and source != 'all':
        # Используем тот же фильтр, но для подзапроса
        # Нам нужно убедиться, что params содержит все src_i
        add_mon = db.execute(text(f"""
            SELECT COALESCE(SUM(am.revenue), 0)
            FROM additional_monetization am
            WHERE am.date >= :date_from AND am.date <= :date_to
              AND am.campaign_id IN (
                  SELECT DISTINCT campaign_id 
                  FROM traffic_stats 
                  WHERE date >= :date_from AND date <= :date_to {source_filter}
              )
        """), params).scalar() or 0
    else:
        add_mon = db.execute(text(
            "SELECT COALESCE(SUM(revenue),0) FROM additional_monetization WHERE date >= :date_from AND date <= :date_to"
        ), {'date_from': date_from, 'date_to': date_to}).scalar() or 0

    add_mon = int(round(float(add_mon or 0)))
    total_profit = total_base_revenue + add_mon - total_spend
    return total_spend, total_base_revenue, add_mon, total_profit, conversions, clicks


@router.get("/metrics/summary")
async def get_summary(
    period: int = Query(7),
    date_from_param: Optional[str] = Query(None, alias="date_from"),
    date_to_param: Optional[str] = Query(None, alias="date_to"),
    source: Optional[str] = None,
    db: Session = Depends(get_db),
):
    date_from, date_to = _period_or_range(period, date_from_param, date_to_param)
    total_spend, total_base_revenue, add_mon, profit, conversions, clicks = _get_totals(db, date_from, date_to, source)
    total_revenue = total_base_revenue + add_mon
    roi = round((profit / total_spend * 100) if total_spend > 0 else 0)
    return {"spend": total_spend, "revenue": total_revenue, "profit": profit, "roi": roi, "conversions": conversions, "clicks": clicks}

@router.get("/metrics/monetization-dashboard")
async def get_monetization_dashboard(
    period: int = Query(7),
    date_from_param: Optional[str] = Query(None, alias="date_from"),
    date_to_param: Optional[str] = Query(None, alias="date_to"),
    source: Optional[str] = None,
    campaign_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    date_from, date_to = _period_or_range(period, date_from_param, date_to_param)
    params = {'date_from': date_from, 'date_to': date_to}
    source_filter = _apply_source_filter(params, source, FILTER_OUT_MONETISATION)
    
    camp_filter = ""
    if campaign_id:
        params['cid_filter'] = campaign_id
        camp_filter = " AND am.campaign_id = :cid_filter"
        ts_camp_filter = " AND campaign_id = :cid_filter"
    else:
        ts_camp_filter = ""

    # Logic for categorization
    cat_sql = """
        CASE 
            WHEN LOWER(am.source) LIKE '%push%' 
                 OR LOWER(am.token1) LIKE '%!_ip%' ESCAPE '!'
                 OR am.campaign_id IN (SELECT campaign_id FROM traffic_stats WHERE (LOWER(campaign) LIKE '%push%' OR LOWER(campaign) LIKE '%!_ip%' ESCAPE '!') AND date >= :date_from AND date <= :date_to) THEN 'push'
            WHEN LOWER(am.source) LIKE '%bb%' OR LOWER(am.source) LIKE '%back%' OR am.campaign_id IN (SELECT campaign_id FROM traffic_stats WHERE (LOWER(campaign) LIKE '%bb%' OR LOWER(campaign) LIKE '%back%') AND date >= :date_from AND date <= :date_to) THEN 'bb'
            ELSE 'double'
        END
    """

    # 1. Categorized Monetization Revenue
    rev_rows = db.execute(text(f"""
        SELECT 
            {cat_sql} as category,
            COALESCE(SUM(am.revenue), 0) as revenue
        FROM additional_monetization am
        WHERE am.date >= :date_from AND am.date <= :date_to {camp_filter}
          AND am.campaign_id IN (
              SELECT DISTINCT campaign_id 
              FROM traffic_stats 
              WHERE date >= :date_from AND date <= :date_to {source_filter} {ts_camp_filter}
          )
        GROUP BY category
    """), params).fetchall()
    
    rev_by_cat = {r[0]: round(r[1], 2) for r in rev_rows}
    total_rev = sum(rev_by_cat.values())
    
    # 2. Bought Jump Clicks (First Base)
    jump_clicks = db.execute(text(f"""
        SELECT COUNT(*) 
        FROM traffic_stats 
        WHERE date >= :date_from AND date <= :date_to 
          AND cost > 0 
          AND lander_id IS NOT NULL AND lander_id != '0' AND lander_id != ''
          {source_filter} {ts_camp_filter}
    """), params).scalar() or 0
    
    # 3. Breakdowns
    by_source = db.execute(text(f"""
        WITH SourceJumps AS (
            SELECT traffic_source, COUNT(*) as jumps, SUM(cost) as cost
            FROM traffic_stats
            WHERE date >= :date_from AND date <= :date_to
              AND cost > 0 AND lander_id IS NOT NULL AND lander_id != '0' AND lander_id != ''
              {source_filter} {ts_camp_filter}
            GROUP BY traffic_source
        ),
        SourceRevenue AS (
            SELECT ts.traffic_source, SUM(am.revenue) as revenue
            FROM additional_monetization am
            JOIN (SELECT DISTINCT campaign_id, traffic_source FROM traffic_stats WHERE date >= :date_from AND date <= :date_to {ts_camp_filter}) ts 
              ON am.campaign_id = ts.campaign_id
            WHERE am.date >= :date_from AND am.date <= :date_to {camp_filter}
            GROUP BY ts.traffic_source
        )
        SELECT sj.traffic_source, sj.jumps, COALESCE(sr.revenue, 0), sj.cost
        FROM SourceJumps sj
        LEFT JOIN SourceRevenue sr ON sj.traffic_source = sr.traffic_source
        ORDER BY COALESCE(sr.revenue, 0) DESC
    """), params).fetchall()
    
    sources_data = [{
        "source": r[0], "jumps": r[1], "revenue": round(r[2], 2),
        "erpm": round((r[2] / (r[1] / 1000)) if r[1] > 0 else 0, 2),
        "cost": round(r[3], 2)
    } for r in by_source]

    by_campaign = db.execute(text(f"""
        WITH CampaignJumps AS (
            SELECT campaign_id, MAX(campaign) as campaign, MAX(token1) as t1, COUNT(*) as jumps, SUM(cost) as cost
            FROM traffic_stats
            WHERE date >= :date_from AND date <= :date_to
              AND cost > 0 AND lander_id IS NOT NULL AND lander_id != '0' AND lander_id != ''
              {source_filter} {ts_camp_filter}
            GROUP BY campaign_id
        ),
        CampaignRevenue AS (
            SELECT campaign_id, SUM(revenue) as revenue
            FROM additional_monetization am
            WHERE am.date >= :date_from AND am.date <= :date_to {camp_filter}
            GROUP BY campaign_id
        )
        SELECT cj.campaign_id, cj.campaign, cj.jumps, COALESCE(cr.revenue, 0), cj.cost, cj.t1
        FROM CampaignJumps cj
        LEFT JOIN CampaignRevenue cr ON cj.campaign_id = cr.campaign_id
        ORDER BY COALESCE(cr.revenue, 0) DESC
        LIMIT 50
    """), params).fetchall()
    
    campaigns_data = [{
        "campaign_id": r[0], 
        "campaign": r[1].replace('Mediabuys - ', '') if r[1] else r[0], 
        "jumps": r[2], 
        "revenue": round(r[3], 2),
        "erpm": round((r[3] / (r[2] / 1000)) if r[2] > 0 else 0, 2),
        "cost": round(r[4], 2),
        "token1": r[5] or ''
    } for r in by_campaign]
    
    return {
        "summary": {
            "revenue": round(total_rev, 2),
            "jumps": jump_clicks,
            "erpm": round((total_rev / (jump_clicks / 1000)) if jump_clicks > 0 else 0, 2),
            "categories": {
                "push": rev_by_cat.get('push', 0),
                "bb": rev_by_cat.get('bb', 0),
                "double": rev_by_cat.get('double', 0)
            }
        },
        "by_source": sources_data,
        "by_campaign": campaigns_data
    }

@router.get("/metrics/monetization-daily")
async def get_monetization_daily(
    period: int = Query(7),
    date_from_param: Optional[str] = Query(None, alias="date_from"),
    date_to_param: Optional[str] = Query(None, alias="date_to"),
    source: Optional[str] = None,
    campaign_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    date_from, date_to = _period_or_range(period, date_from_param, date_to_param)
    params = {'date_from': date_from, 'date_to': date_to}
    source_filter = _apply_source_filter(params, source, FILTER_OUT_MONETISATION)
    
    camp_filter = ""
    if campaign_id:
        params['cid_filter'] = campaign_id
        camp_filter = " AND am.campaign_id = :cid_filter"
        ts_camp_filter = " AND campaign_id = :cid_filter"
    else:
        ts_camp_filter = ""

    cat_sql = """
        CASE 
            WHEN LOWER(am.source) LIKE '%push%' 
                 OR LOWER(am.token1) LIKE '%!_ip%' ESCAPE '!'
                 OR am.campaign_id IN (SELECT campaign_id FROM traffic_stats WHERE (LOWER(campaign) LIKE '%push%' OR LOWER(campaign) LIKE '%!_ip%' ESCAPE '!') AND date >= :date_from AND date <= :date_to) THEN 'push'
            WHEN LOWER(am.source) LIKE '%bb%' OR LOWER(am.source) LIKE '%back%' OR am.campaign_id IN (SELECT campaign_id FROM traffic_stats WHERE (LOWER(campaign) LIKE '%bb%' OR LOWER(campaign) LIKE '%back%') AND date >= :date_from AND date <= :date_to) THEN 'bb'
            ELSE 'double'
        END
    """

    daily_jumps = db.execute(text(f"""
        SELECT date, COUNT(*) as jumps FROM traffic_stats
        WHERE date >= :date_from AND date <= :date_to
          AND cost > 0 AND lander_id IS NOT NULL AND lander_id != '0' AND lander_id != ''
          {source_filter} {ts_camp_filter}
        GROUP BY date
    """), params).fetchall()
    
    daily_rev = db.execute(text(f"""
        WITH ActiveCampaigns AS (
            SELECT DISTINCT campaign_id FROM traffic_stats 
            WHERE date >= :date_from AND date <= :date_to {source_filter} {ts_camp_filter}
        )
        SELECT am.date, {cat_sql} as cat, SUM(am.revenue) as revenue
        FROM additional_monetization am
        JOIN ActiveCampaigns ac ON am.campaign_id = ac.campaign_id
        WHERE am.date >= :date_from AND am.date <= :date_to {camp_filter}
        GROUP BY am.date, cat
    """), params).fetchall()
    
    jumps_dict = {row[0]: row[1] for row in daily_jumps}
    rev_map = {} # date -> {cat -> rev}
    for row in daily_rev:
        d, c, r = row[0], row[1], row[2]
        if d not in rev_map: rev_map[d] = {}
        rev_map[d][c] = r
    
    daily_data = []
    current_date = date_from
    while current_date <= date_to:
        d_str = current_date.strftime('%Y-%m-%d')
        j = jumps_dict.get(d_str, 0)
        rd = rev_map.get(d_str, {})
        
        daily_data.append({
            "date": d_str,
            "jumps": j,
            "revenue": round(sum(rd.values()), 2),
            "push_rev": round(rd.get('push', 0), 2),
            "bb_rev": round(rd.get('bb', 0), 2),
            "double_rev": round(rd.get('double', 0), 2),
            "erpm": round((sum(rd.values()) / (j / 1000)) if j > 0 else 0, 2)
        })
        current_date += timedelta(days=1)
        
    return {"daily": daily_data}

@router.get("/metrics/campaigns")
async def get_campaigns(
    period: int = Query(7),
    date_from_param: Optional[str] = Query(None, alias="date_from"),
    date_to_param: Optional[str] = Query(None, alias="date_to"),
    source: Optional[str] = None,
    min_cost: int = Query(0, description="Minimum spend filter (e.g. 20 for $20)"),
    db: Session = Depends(get_db),
):
    date_from, date_to = _period_or_range(period, date_from_param, date_to_param)
    params = {'date_from': date_from, 'date_to': date_to}
    source_filter = _apply_source_filter(params, source)
    
    having = " HAVING SUM(cost) >= :min_cost" if min_cost > 0 else ""
    if min_cost > 0:
        params['min_cost'] = min_cost

    limit_val = 500 if min_cost > 0 else 50
    query = text(
        f"SELECT campaign_id, MAX(campaign), traffic_source, SUM(cost), SUM(revenue), SUM(conversions), COUNT(*) "
        f"FROM traffic_stats WHERE date >= :date_from AND date <= :date_to {source_filter} "
        f"GROUP BY campaign_id, traffic_source{having} ORDER BY SUM(revenue)-SUM(cost) DESC LIMIT {limit_val}"
    )
    rows = db.execute(query, params).fetchall()
    campaigns = []
    for row in rows:
        spend, revenue = int(row[3] or 0), int(row[4] or 0)
        profit = revenue - spend
        roi = round((profit / spend * 100) if spend > 0 else 0)
        campaign_name = row[1].replace('Mediabuys - ', '') if row[1] else row[0]
        campaigns.append({"campaign_id": row[0], "campaign": campaign_name, "source": row[2], "spend": spend, "revenue": revenue, "profit": profit, "roi": roi, "conversions": int(row[5] or 0), "clicks": int(row[6] or 0)})
    return {"campaigns": campaigns}


def get_campaign_breakdown_data(
    db: Session,
    campaign_id: str,
    date_from: date,
    date_to: date,
) -> Dict[str, Any]:
    """Возвращает breakdown по кампании (для внутреннего использования)."""
    params = {"cid": campaign_id, "d": date_from, "d_to": date_to}
    row = db.execute(
        text("""
            SELECT SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
            FROM traffic_stats
            WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        """),
        params,
    ).fetchone()
    spend = int(round(float(row[0] or 0)))
    base_revenue = int(round(float(row[1] or 0)))
    conversions = int(row[2] or 0)
    clicks = int(row[3] or 0)
    add_mon = db.execute(
        text("SELECT COALESCE(SUM(revenue),0) FROM additional_monetization WHERE campaign_id = :cid AND date >= :d AND date <= :d_to"),
        params,
    ).scalar() or 0
    revenue = base_revenue + int(add_mon)
    profit = revenue - spend
    roi = round((profit / spend * 100) if spend > 0 else 0)
    epc = round(revenue / clicks, 4) if clicks else 0
    cr = round(conversions / clicks * 100, 2) if clicks else 0
    summary = {
        "campaign_id": campaign_id,
        "spend": spend,
        "revenue": revenue,
        "profit": profit,
        "roi": roi,
        "conversions": conversions,
        "clicks": clicks,
        "epc": epc,
        "cr_pct": cr,
    }

    def _rows(rows, first_key="name"):
        out = []
        for r in rows:
            s, rev, conv, clk = int(r[1] or 0), int(r[2] or 0), int(r[3] or 0), int(r[4] or 0)
            out.append({
                first_key: r[0] or "(empty)",
                "spend": s, "revenue": rev, "conversions": conv, "clicks": clk,
                "epc": round(rev / clk, 4) if clk else 0,
                "cr_pct": round(conv / clk * 100, 2) if clk else 0,
                "profit": rev - s,
            })
        return out

    by_token2 = db.execute(text("""
        SELECT COALESCE(token2, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY token2 ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 50
    """), params).fetchall()
    by_offer = db.execute(text("""
        SELECT COALESCE(offer, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY offer ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 50
    """), params).fetchall()
    by_lander = db.execute(text("""
        SELECT COALESCE(lander_id, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY lander_id ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 50
    """), params).fetchall()
    by_os = db.execute(text("""
        SELECT COALESCE(os, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY os ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 30
    """), params).fetchall()
    by_country = db.execute(text("""
        SELECT COALESCE(country, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY country ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 30
    """), params).fetchall()
    by_device_type = db.execute(text("""
        SELECT COALESCE(device_type, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY device_type ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 30
    """), params).fetchall()
    by_path = db.execute(text("""
        SELECT COALESCE(path, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY path ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 30
    """), params).fetchall()
    by_rule = db.execute(text("""
        SELECT COALESCE(rule, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY rule ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 30
    """), params).fetchall()
    by_token3 = db.execute(text("""
        SELECT COALESCE(token3, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY token3 ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 30
    """), params).fetchall()
    by_token4 = db.execute(text("""
        SELECT COALESCE(token4, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY token4 ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 30
    """), params).fetchall()
    by_token5 = db.execute(text("""
        SELECT COALESCE(token5, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY token5 ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 30
    """), params).fetchall()
    by_token6 = db.execute(text("""
        SELECT COALESCE(token6, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY token6 ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 30
    """), params).fetchall()
    by_token7 = db.execute(text("""
        SELECT COALESCE(token7, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY token7 ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 30
    """), params).fetchall()
    by_token8 = db.execute(text("""
        SELECT COALESCE(token8, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY token8 ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 30
    """), params).fetchall()
    by_token9 = db.execute(text("""
        SELECT COALESCE(token9, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY token9 ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 30
    """), params).fetchall()
    by_token10 = db.execute(text("""
        SELECT COALESCE(token10, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY token10 ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 30
    """), params).fetchall()
    by_os_version = db.execute(text("""
        SELECT COALESCE(os_version, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY os_version ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 30
    """), params).fetchall()
    by_browser_name = db.execute(text("""
        SELECT COALESCE(browser_name, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY browser_name ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 30
    """), params).fetchall()
    by_language = db.execute(text("""
        SELECT COALESCE(language, '(empty)'), SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY language ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 30
    """), params).fetchall()
    combo = db.execute(text("""
        SELECT COALESCE(token2, '(empty)'), COALESCE(offer, '(empty)'), COALESCE(lander_id, '(empty)'),
               SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY token2, offer, lander_id HAVING COUNT(*) >= 1
        ORDER BY SUM(revenue) - SUM(cost) DESC LIMIT 30
    """), params).fetchall()
    combinations = [
        {
            "token2": r[0] or "(empty)",
            "offer_id": r[1] or "(empty)",
            "lander_id": r[2] or "(empty)",
            "spend": int(r[3] or 0), "revenue": int(r[4] or 0),
            "conversions": int(r[5] or 0), "clicks": int(r[6] or 0),
            "epc": round(int(r[4] or 0) / (int(r[6] or 0) or 1), 4),
            "cr_pct": round(int(r[5] or 0) / (int(r[6] or 0) or 1) * 100, 2),
            "profit": int(r[4] or 0) - int(r[3] or 0),
        }
        for r in combo
    ]
    path_offer_combo = db.execute(text("""
        SELECT COALESCE(path, '(empty)'), COALESCE(rule, '(empty)'), COALESCE(offer, '(empty)'), COALESCE(lander_id, '(empty)'),
               SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
        FROM traffic_stats
        WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
        GROUP BY path, rule, offer, lander_id
        HAVING COUNT(*) >= 1
        ORDER BY SUM(revenue) - SUM(cost) DESC
        LIMIT 50
    """), params).fetchall()
    path_offer_lander = [
        {
            "path": r[0] or "(empty)",
            "rule": r[1] or "(empty)",
            "offer_id": r[2] or "(empty)",
            "lander_id": r[3] or "(empty)",
            "spend": int(r[4] or 0),
            "revenue": int(r[5] or 0),
            "conversions": int(r[6] or 0),
            "clicks": int(r[7] or 0),
            "profit": int(r[5] or 0) - int(r[4] or 0),
            "roi": round((int(r[5] or 0) - int(r[4] or 0)) / int(r[4] or 1) * 100) if int(r[4] or 0) != 0 else 0,
        }
        for r in path_offer_combo
    ]
    column_labels = {
        "token2": "Token 2 (creative)", "offer_id": "Offer ID", "lander_id": "Lander ID (jump)",
        "os": "OS", "country": "Country", "device_type": "Device Type",
        "traffic_source": "Traffic Source", "campaign_id": "Campaign ID", "path": "Path", "rule": "Rule",
        "token1": "Token 1", "token3": "Token 3", "token4": "Token 4", "token5": "Token 5",
        "token6": "Token 6", "token7": "Token 7", "token8": "Token 8", "token9": "Token 9", "token10": "Token 10",
        "cost": "Cost", "revenue": "Payout", "conversions": "Conversion", "clicks": "clicks (count)",
        "epc": "EPC ($)", "cr_pct": "CR (%)", "profit": "profit ($)",
    }
    return {
        "column_labels": column_labels,
        "summary": summary,
        "by_token2": _rows(by_token2),
        "by_token3": _rows(by_token3, first_key="token3"),
        "by_token4": _rows(by_token4, first_key="token4"),
        "by_token5": _rows(by_token5, first_key="token5"),
        "by_token6": _rows(by_token6, first_key="token6"),
        "by_token7": _rows(by_token7, first_key="token7"),
        "by_token8": _rows(by_token8, first_key="token8"),
        "by_token9": _rows(by_token9, first_key="token9"),
        "by_token10": _rows(by_token10, first_key="token10"),
        "by_offer_id": _rows(by_offer, first_key="offer_id"),
        "by_lander_id_jump": _rows(by_lander, first_key="lander_id"),
        "by_os": _rows(by_os, first_key="os"),
        "by_country": _rows(by_country, first_key="country"),
        "by_device_type": _rows(by_device_type, first_key="device_type"),
        "by_path": _rows(by_path, first_key="path"),
        "by_rule": _rows(by_rule, first_key="rule"),
        "by_os_version": _rows(by_os_version, first_key="os_version"),
        "by_browser_name": _rows(by_browser_name, first_key="browser_name"),
        "by_language": _rows(by_language, first_key="language"),
        "top_combinations_token2_offer_id_jump": combinations,
        "path_offer_lander": path_offer_lander,
    }


@router.get("/metrics/campaign-breakdown")
async def get_campaign_breakdown(
    campaign_id: str = Query(..., description="Campaign ID (token1)"),
    period: int = Query(14),
    date_from_param: Optional[str] = Query(None, alias="date_from"),
    date_to_param: Optional[str] = Query(None, alias="date_to"),
    db: Session = Depends(get_db),
):
    """
    Разбивка по кампании для ИИ: token2 (creative), offer, lander_id (jump).
    Реальные данные из БД — чтобы модель не «фантазировала», а опиралась на цифры.
    """
    date_from, date_to = _period_or_range(period, date_from_param, date_to_param)
    return get_campaign_breakdown_data(db, campaign_id, date_from, date_to)


@router.get("/metrics/sources")
async def get_sources(
    period: int = Query(7),
    date_from_param: Optional[str] = Query(None, alias="date_from"),
    date_to_param: Optional[str] = Query(None, alias="date_to"),
    db: Session = Depends(get_db)
):
    if period == 0:
        # Fetch all time
        result = db.execute(text(
            f"SELECT traffic_source FROM traffic_stats "
            f"WHERE traffic_source IS NOT NULL {FILTER_OUT_MONETISATION} "
            f"GROUP BY traffic_source "
            f"HAVING SUM(cost) >= 10 "
            f"ORDER BY traffic_source"
        )).fetchall()
    else:
        date_from, date_to = _period_or_range(period, date_from_param, date_to_param)
        result = db.execute(text(
            f"SELECT traffic_source FROM traffic_stats "
            f"WHERE date >= :d AND date <= :d_to AND traffic_source IS NOT NULL {FILTER_OUT_MONETISATION} "
            f"GROUP BY traffic_source "
            f"HAVING SUM(cost) >= 10 "
            f"ORDER BY traffic_source"
        ), {'d': date_from, 'd_to': date_to}).fetchall()

        
    return {"sources": [r[0] for r in result]}

@router.get("/metrics/daily")
async def get_daily(
    period: int = Query(14),
    date_from_param: Optional[str] = Query(None, alias="date_from"),
    date_to_param: Optional[str] = Query(None, alias="date_to"),
    source: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    General Dynamics: данные за выбранный период или кастомный диапазон.
    """
    date_from, date_to = _period_or_range(period, date_from_param, date_to_param)
    params = {"d": date_from, "d_to": date_to}
    source_filter = _apply_source_filter(params, source, FILTER_OUT_MONETISATION)
    
    rows = db.execute(
        text(f"""
        SELECT date, SUM(cost), SUM(revenue), SUM(conversions), COUNT(*) as clicks
        FROM traffic_stats
        WHERE date >= :d AND date <= :d_to AND traffic_source IS NOT NULL {source_filter}
        GROUP BY date
        ORDER BY date
        """),
        params,
    ).fetchall()
    by_date = {str(row[0]): {"cost": int(row[1] or 0), "revenue": int(row[2] or 0), "conversions": int(row[3] or 0), "clicks": int(row[4] or 0)} for row in rows}

    # Добавляем доп. монетизацию по дням
    if source and source != "all":
        add_mon_rows = db.execute(text(f"""
            SELECT date, SUM(revenue)
            FROM additional_monetization
            WHERE date >= :d AND date <= :d_to
              AND campaign_id IN (SELECT DISTINCT campaign_id FROM traffic_stats WHERE date >= :d AND date <= :d_to {source_filter})
            GROUP BY date
        """), params).fetchall()
    else:
        add_mon_rows = db.execute(text("""
            SELECT date, SUM(revenue)
            FROM additional_monetization
            WHERE date >= :d AND date <= :d_to
            GROUP BY date
        """), params).fetchall()

    for row in add_mon_rows:
        d_str = str(row[0])
        if d_str in by_date:
            by_date[d_str]["revenue"] += int(round(float(row[1] or 0)))
        else:
            by_date[d_str] = {"cost": 0, "revenue": int(round(float(row[1] or 0))), "conversions": 0, "clicks": 0}

    daily = []
    days_count = (date_to - date_from).days + 1
    for i in range(days_count):
        d = date_from + timedelta(days=i)
        rec = by_date.get(d.isoformat(), {"cost": 0, "revenue": 0, "conversions": 0, "clicks": 0})
        daily.append({
            "date": d.isoformat(),
            "cost": rec["cost"],
            "revenue": rec["revenue"],
            "profit": rec["revenue"] - rec["cost"],
            "conversions": rec["conversions"],
            "clicks": rec["clicks"],
        })
    return {"daily": daily}

@router.get("/metrics/sources-table")
async def get_sources_table(
    period: int = Query(14),
    date_from_param: Optional[str] = Query(None, alias="date_from"),
    date_to_param: Optional[str] = Query(None, alias="date_to"),
    db: Session = Depends(get_db),
):
    date_from, date_to = _period_or_range(period, date_from_param, date_to_param)
    sources = db.execute(text(
        f"SELECT traffic_source FROM traffic_stats "
        f"WHERE date >= :d AND date <= :d_to AND traffic_source IS NOT NULL {FILTER_OUT_MONETISATION} "
        f"GROUP BY traffic_source "
        f"HAVING SUM(cost) >= 10"
    ), {'d': date_from, 'd_to': date_to}).fetchall()

    result = []
    for (src,) in sources:
        daily = db.execute(text("SELECT date, SUM(cost), SUM(revenue) FROM traffic_stats WHERE traffic_source = :s AND date >= :d AND date <= :d_to GROUP BY date ORDER BY date"), {'s': src, 'd': date_from, 'd_to': date_to}).fetchall()
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
    return {"sources": result, "date_from": date_from.isoformat(), "date_to": date_to.isoformat()}

@router.get("/metrics/splits")
async def get_splits(
    period: int = Query(14),
    date_from_param: Optional[str] = Query(None, alias="date_from"),
    date_to_param: Optional[str] = Query(None, alias="date_to"),
    source: Optional[str] = None,
    db: Session = Depends(get_db),
):
    date_from, date_to = _period_or_range(period, date_from_param, date_to_param)
    total_spend, total_base_revenue, add_mon, total_profit, _, _ = _get_totals(db, date_from, date_to, source)

    params = {'date_from': date_from, 'date_to': date_to}
    source_filter = _apply_source_filter(params, source, FILTER_OUT_MONETISATION)

    # 1. OS Split
    os_raw = db.execute(text(f"""
        SELECT COALESCE(os, 'Unknown'), COUNT(*), SUM(cost), SUM(revenue)
        FROM traffic_stats WHERE date >= :date_from AND date <= :date_to AND traffic_source IS NOT NULL {source_filter}
        GROUP BY COALESCE(os, 'Unknown')
    """), params).fetchall()

    total_os_clicks = sum(int(row[1] or 0) for row in os_raw)
    
    # Считаем веса OS для каждой кампании
    campaign_os_weights = db.execute(text(f"""
        SELECT 
            campaign_id, 
            COALESCE(os, 'Unknown') as os,
            CAST(COUNT(*) AS FLOAT) / SUM(COUNT(*)) OVER (PARTITION BY campaign_id) as weight
        FROM traffic_stats
        WHERE date >= :date_from AND date <= :date_to
        GROUP BY campaign_id, os
    """), params).fetchall()
    
    weights_map = {}
    for cid, os_name, weight in campaign_os_weights:
        if cid not in weights_map: weights_map[cid] = {}
        weights_map[cid][os_name] = weight

    # Распределяем доп. монетизацию
    add_mon_rows = db.execute(text("""
        SELECT campaign_id, SUM(revenue)
        FROM additional_monetization
        WHERE date >= :date_from AND date <= :date_to
        GROUP BY campaign_id
    """), params).fetchall()
    
    os_add_mon = {"Android": 0, "Other": 0, "iOS": 0}
    for cid, rev in add_mon_rows:
        rev = float(rev or 0)
        c_weights = weights_map.get(cid, {"Other": 1.0})
        for os_name, weight in c_weights.items():
            mapped_os = "iOS" if os_name == "iOS" else "Android" if os_name == "Android" else "Other"
            os_add_mon[mapped_os] += rev * weight

    os_groups = {"Android": {"clicks": 0, "profit": 0}, "Other": {"clicks": 0, "profit": 0}, "iOS": {"clicks": 0, "profit": 0}}
    for row in os_raw:
        os_name = (str(row[0] or 'Unknown')).strip() or 'Unknown'
        mapped_os = "iOS" if os_name == "iOS" else "Android" if os_name == "Android" else "Other"
        clicks = int(row[1] or 0)
        cost = int(round(float(row[2] or 0)))
        rev = int(round(float(row[3] or 0)))
        os_groups[mapped_os]["clicks"] += clicks
        os_groups[mapped_os]["profit"] += (rev - cost)
    
    for name in os_groups:
        os_groups[name]["profit"] += int(round(os_add_mon[name]))

    os_result = []
    for name in ["Android", "Other", "iOS"]:
        data = os_groups[name]
        traffic_pct = round(data["clicks"] / total_os_clicks * 100) if total_os_clicks > 0 else 0
        profit_pct = round(data["profit"] / total_profit * 100) if total_profit != 0 else 0
        os_result.append({"name": name, "clicks": data["clicks"], "traffic_pct": traffic_pct, "profit": data["profit"], "profit_pct": profit_pct})

    # 2. Device Split
    device_raw = db.execute(text(f"""
        SELECT COALESCE(device_type, 'Unknown'), COUNT(*), SUM(cost), SUM(revenue)
        FROM traffic_stats WHERE date >= :date_from AND date <= :date_to AND traffic_source IS NOT NULL {source_filter}
        GROUP BY COALESCE(device_type, 'Unknown')
    """), params).fetchall()

    total_dev_clicks = sum(int(row[1] or 0) for row in device_raw)
    
    campaign_dev_weights = db.execute(text(f"""
        SELECT 
            campaign_id, 
            COALESCE(device_type, 'Unknown') as dev,
            CAST(COUNT(*) AS FLOAT) / SUM(COUNT(*)) OVER (PARTITION BY campaign_id) as weight
        FROM traffic_stats
        WHERE date >= :date_from AND date <= :date_to
        GROUP BY campaign_id, device_type
    """), params).fetchall()
    
    dev_weights_map = {}
    for cid, dev_name, weight in campaign_dev_weights:
        if cid not in dev_weights_map: dev_weights_map[cid] = {}
        dev_weights_map[cid][dev_name] = weight

    dev_add_mon = {}
    for cid, rev in add_mon_rows:
        rev = float(rev or 0)
        c_weights = dev_weights_map.get(cid, {"Unknown": 1.0})
        for dev_name, weight in c_weights.items():
            dev_add_mon[dev_name] = dev_add_mon.get(dev_name, 0) + (rev * weight)

    device_groups = {"Mobile": {"clicks": 0, "profit": 0}, "Desktop": {"clicks": 0, "profit": 0}, "Other": {"clicks": 0, "profit": 0}}
    for row in device_raw:
        dev_name = (str(row[0] or 'Unknown')).strip() or 'Unknown'
        clicks = int(row[1] or 0)
        cost = int(round(float(row[2] or 0)))
        rev = int(round(float(row[3] or 0)))
        add_rev = dev_add_mon.get(dev_name, 0)
        profit = int(round(rev + add_rev - cost))
        
        if dev_name == "Mobile":
            device_groups["Mobile"]["clicks"] += clicks
            device_groups["Mobile"]["profit"] += profit
        elif dev_name == "Desktop":
            device_groups["Desktop"]["clicks"] += clicks
            device_groups["Desktop"]["profit"] += profit
        else:
            device_groups["Other"]["clicks"] += clicks
            device_groups["Other"]["profit"] += profit

    device_result = []
    for name in ["Mobile", "Desktop", "Other"]:
        data = device_groups[name]
        traffic_pct = round(data["clicks"] / total_dev_clicks * 100) if total_dev_clicks > 0 else 0
        profit_pct = round(data["profit"] / total_profit * 100) if total_profit != 0 else 0
        device_result.append({"name": name, "clicks": data["clicks"], "traffic_pct": traffic_pct, "profit": data["profit"], "profit_pct": profit_pct})

    return {"os": os_result, "device": device_result}





@router.get("/orphans")
async def get_orphans(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT id, token1, date, revenue, source FROM orphans")).fetchall()
    
    def format_date(d):
        if not d: return None
        if isinstance(d, str): return d
        try: return d.isoformat()
        except: return str(d)

    groups = {}
    for r in rows:
        t = str(r[1])
        parts = t.split('_')
        # Берем первые два префикса (например, 2157_y)
        prefix = '_'.join(parts[:2]) if len(parts) >= 2 else t
        
        if prefix not in groups:
            groups[prefix] = {
                "id": r[0],
                "token1": prefix,
                "revenue": 0.0,
                "sources": set(),
                "date": format_date(r[2])
            }
        
        groups[prefix]["revenue"] += float(r[3] or 0)
        if r[4]:
            groups[prefix]["sources"].add(str(r[4]))
            
    orphans = []
    total_count = 0
    total_revenue = 0.0
    
    for p, g in groups.items():
        if g["revenue"] > 0:
            total_count += 1
            total_revenue += g["revenue"]
            orphans.append({
                "id": g["id"],
                "token1": g["token1"],
                "date": g["date"],
                "revenue": round(g["revenue"], 2),
                "source": " / ".join(sorted(list(g["sources"])))
            })
        
    orphans.sort(key=lambda x: x["revenue"], reverse=True)
    orphans = orphans[:100]

    return {"orphans": orphans, "total_count": total_count, "total_revenue": round(total_revenue, 2)}

@router.post("/orphans/match")
async def match_orphan(orphan_id: int, campaign_id: str, db: Session = Depends(get_db)):
    target = db.execute(text("SELECT token1 FROM orphans WHERE id = :id"), {"id": orphan_id}).fetchone()
    if not target:
        return {"success": False, "error": "Orphan not found"}
        
    t = str(target[0])
    parts = t.split('_')
    target_prefix = '_'.join(parts[:2]) if len(parts) >= 2 else t
    
    all_orphans = db.execute(text("SELECT id, token1, date, revenue, source FROM orphans")).fetchall()
    
    matched_count = 0
    for r in all_orphans:
        r_t = str(r[1])
        r_parts = r_t.split('_')
        r_prefix = '_'.join(r_parts[:2]) if len(r_parts) >= 2 else r_t
        
        if r_prefix == target_prefix:
            db.execute(text("INSERT INTO additional_monetization (campaign_id, token1, date, revenue, source) VALUES (:cid, :t, :d, :r, :s)"), 
                       {"cid": campaign_id, "t": r[1], "d": r[2], "r": r[3], "s": r[4]})
            db.execute(text("DELETE FROM orphans WHERE id = :id"), {"id": r[0]})
            matched_count += 1
            
    db.commit()
    return {"success": True, "matched": matched_count}

@router.get("/metrics/traffic-sources-summary")
async def get_traffic_sources_summary(
    period: int = Query(14),
    date_from_param: Optional[str] = Query(None, alias="date_from"),
    date_to_param: Optional[str] = Query(None, alias="date_to"),
    source: Optional[str] = None,
    db: Session = Depends(get_db),
):
    date_from, date_to = _period_or_range(period, date_from_param, date_to_param)
    params = {'d': date_from, 'd_to': date_to}
    source_filter = _apply_source_filter(params, source)

    # additional_monetization за период (при выборе источника — только кампании этого источника)
    if source and source != "all":
        total_add = float(db.execute(text(f"""
            SELECT COALESCE(SUM(am.revenue), 0)
            FROM additional_monetization am
            WHERE am.date >= :d AND am.date <= :d_to
              AND am.campaign_id IN (SELECT DISTINCT campaign_id FROM traffic_stats WHERE date >= :d AND date <= :d_to {source_filter})
        """), params).scalar() or 0)
    else:
        total_add = float(db.execute(text(
            "SELECT COALESCE(SUM(revenue),0) FROM additional_monetization WHERE date >= :d AND date <= :d_to"
        ), params).scalar() or 0)

    # 1. Получаем базовые метрики (spend, base_revenue) из traffic_stats
    sources_raw = db.execute(text(f"""
        SELECT 
            traffic_source,
            SUM(cost) as spend,
            SUM(revenue) as base_revenue
        FROM traffic_stats
        WHERE date >= :d AND date <= :d_to
          AND traffic_source IS NOT NULL 
          {FILTER_OUT_MONETISATION if not (source and source != "all") else ""}
          {source_filter}
        GROUP BY traffic_source
    """), params).fetchall()
    
    # 2. Получаем реальную доп. монетизацию по каждому источнику
    # Группируем по источнику, находя его через campaign_id в traffic_stats
    add_mon_by_source = db.execute(text(f"""
        SELECT 
            ts.traffic_source,
            SUM(am.revenue) as add_rev
        FROM additional_monetization am
        JOIN (SELECT DISTINCT campaign_id, traffic_source FROM traffic_stats WHERE date >= :d AND date <= :d_to {source_filter}) ts 
          ON am.campaign_id = ts.campaign_id
        WHERE am.date >= :d AND am.date <= :d_to
        GROUP BY ts.traffic_source
    """), params).fetchall()
    
    add_mon_map = {row[0]: float(row[1] or 0) for row in add_mon_by_source}
    
    result = []
    for row in sources_raw:
        source_name = row[0]
        spend = int(row[1] or 0)
        base_revenue = float(row[2] or 0)
        add_revenue = add_mon_map.get(source_name, 0.0)
        
        total_revenue = int(round(base_revenue + add_revenue))
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
async def get_campaigns_table(
    period: int = Query(14),
    date_from_param: Optional[str] = Query(None, alias="date_from"),
    date_to_param: Optional[str] = Query(None, alias="date_to"),
    source: Optional[str] = None,
    db: Session = Depends(get_db),
):
    date_from, date_to = _period_or_range(period, date_from_param, date_to_param)
    # Для SQLite даты должны быть строками
    params = {'d': str(date_from), 'd_to': str(date_to)}
    source_filter = _apply_source_filter(params, source)

    # 1. Находим ТОП-25 по суммарному доходу (Base + AddMon), включая те, где нет спенда
    top_campaigns_query = f"""
        WITH all_cids AS (
            SELECT DISTINCT campaign_id FROM traffic_stats 
            WHERE date >= :d AND date <= :d_to AND campaign_id IS NOT NULL {source_filter}
            UNION
            SELECT DISTINCT campaign_id FROM additional_monetization
            WHERE date >= :d AND date <= :d_to AND campaign_id IS NOT NULL
              AND campaign_id IN (SELECT DISTINCT campaign_id FROM traffic_stats WHERE date >= :d AND date <= :d_to {source_filter})
        ),
        campaign_base AS (
            SELECT 
                ts.campaign_id, 
                MAX(CASE WHEN INSTR(ts.token1, '_') > 0 THEN ts.token1 ELSE NULL END) as token1, 
                MAX(ts.campaign) as name,
                SUM(ts.cost) as total_spend,
                SUM(ts.revenue) as base_revenue
            FROM traffic_stats ts
            JOIN all_cids ac ON ts.campaign_id = ac.campaign_id
            WHERE ts.date >= :d AND ts.date <= :d_to {source_filter}
            GROUP BY ts.campaign_id
        ),
        campaign_add AS (
            SELECT 
                am.campaign_id,
                SUM(am.revenue) as add_revenue
            FROM additional_monetization am
            JOIN all_cids ac ON am.campaign_id = ac.campaign_id
            WHERE am.date >= :d AND am.date <= :d_to
            GROUP BY am.campaign_id
        )
        SELECT 
            ac.campaign_id, 
            COALESCE(cb.token1, ac.campaign_id) as token1, 
            COALESCE(cb.name, 'Campaign ' || ac.campaign_id) as name, 
            COALESCE(cb.total_spend, 0) as total_spend,
            (COALESCE(cb.base_revenue, 0) + COALESCE(ca.add_revenue, 0)) as total_rev
        FROM all_cids ac
        LEFT JOIN campaign_base cb ON ac.campaign_id = cb.campaign_id
        LEFT JOIN campaign_add ca ON ac.campaign_id = ca.campaign_id
        ORDER BY total_spend DESC, total_rev DESC
        LIMIT 25
    """

    campaigns = db.execute(text(top_campaigns_query), params).fetchall()

    result = []
    for row in campaigns:
        # row: (campaign_id, token1, name, total_spend, total_rev)
        cid = row[0]
        token1_val = row[1]
        c_name = row[2]
        total_spend_val = int(row[3] or 0)
        
        day_params = {**params, 'cid': cid}

        
        # Собираем данные из трафика и монетизации по дням
        daily_traffic = db.execute(text(f"""
            SELECT date, SUM(cost), SUM(revenue)
            FROM traffic_stats 
            WHERE campaign_id = :cid AND date >= :d AND date <= :d_to {source_filter}
            GROUP BY date
        """), day_params).fetchall()
        
        daily_add = db.execute(text("""
            SELECT date, SUM(revenue)
            FROM additional_monetization
            WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
            GROUP BY date
        """), day_params).fetchall()
        
        # Мержим по дням
        by_day = {}
        for r in daily_traffic:
            d_str = str(r[0])
            by_day[d_str] = {"spend": float(r[1] or 0), "rev": float(r[2] or 0)}
        
        for r in daily_add:
            d_str = str(r[0])
            if d_str not in by_day:
                by_day[d_str] = {"spend": 0, "rev": 0}
            by_day[d_str]["rev"] += float(r[1] or 0)

        days_dict = {}
        for d_str, vals in by_day.items():
            try:
                from datetime import datetime
                # Учитываем формат даты из SQLite
                d_obj = datetime.fromisoformat(d_str[:10])
                day_key = d_obj.strftime('%m-%d')
            except:
                day_key = d_str
            
            d_spend = int(round(vals["spend"]))
            d_rev = int(round(vals["rev"]))
            d_profit = d_rev - d_spend
            
            d_profit_pct = (d_profit / d_spend * 100) if d_spend > 0 else (100 if d_profit > 0 else 0)
            color = 'green' if d_profit_pct > 10 else 'red' if d_profit_pct < -10 else 'none'
            days_dict[day_key] = {"profit": d_profit, "color": color}

        result.append({
            "campaign_id": cid,
            "token1": token1_val,
            "campaign": c_name,
            "spend": total_spend_val,
            "days": days_dict
        })


    
    return {'campaigns': result, 'date_from': date_from.strftime('%Y-%m-%d')}


def get_campaign_daily_days(
    db: Session,
    campaign_id: str,
    date_from: date,
    date_to: date,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Возвращает days[MM-DD] = {profit, color} для внутреннего использования."""
    params = {'cid': campaign_id, 'd': date_from, 'd_to': date_to}
    source_filter = _apply_source_filter(params, source)

    daily_query = f"""
        SELECT date, SUM(cost), SUM(revenue)
        FROM traffic_stats
        WHERE campaign_id = :cid AND date >= :d AND date <= :d_to {source_filter}
        GROUP BY date
        ORDER BY date
    """
    daily = db.execute(text(daily_query), params).fetchall()
    days = {}
    for day_row in daily:
        d_val = day_row[0]
        if isinstance(d_val, str):
            from datetime import datetime
            d_obj = datetime.fromisoformat(d_val)
        else:
            d_obj = d_val
        day_date = d_obj.strftime('%m-%d')
        day_spend = int(day_row[1] or 0)
        day_base_revenue = int(day_row[2] or 0)
        day_add_revenue = db.execute(text("""
            SELECT COALESCE(SUM(revenue), 0)
            FROM additional_monetization
            WHERE campaign_id = :cid AND date = :dt
        """), {'cid': campaign_id, 'dt': day_row[0]}).scalar() or 0
        day_total_revenue = day_base_revenue + int(day_add_revenue)
        day_profit = day_total_revenue - day_spend
        day_profit_pct = (day_profit / day_spend * 100) if day_spend > 0 else 0
        color = 'red' if day_profit_pct < -10 else ('green' if day_profit_pct > 10 else 'none')
        days[day_date] = {'profit': day_profit, 'color': color}
    return days


@router.get("/metrics/campaign-daily-row")
async def get_campaign_daily_row(
    campaign_id: str = Query(..., description="Campaign ID"),
    period: int = Query(14),
    date_from_param: Optional[str] = Query(None, alias="date_from"),
    date_to_param: Optional[str] = Query(None, alias="date_to"),
    source: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Динамика по одной кампании: days[MM-DD] = {profit, color}.
    last14: суммарные метрики за последние 14 дней.
    """
    date_from, date_to = _period_or_range(period, date_from_param, date_to_param)
    params = {'cid': campaign_id, 'd': date_from, 'd_to': date_to}
    source_filter = _apply_source_filter(params, source)


    # Campaign name and total spend for the period
    meta = db.execute(text(f"""
        SELECT campaign, SUM(cost), SUM(revenue)
        FROM traffic_stats
        WHERE campaign_id = :cid AND date >= :d AND date <= :d_to {source_filter}
        GROUP BY campaign
    """), params).fetchone()
    if not meta:
        return {"found": False, "campaign_id": campaign_id}

    campaign_name = meta[0] or campaign_id
    total_spend = int(meta[1] or 0)
    total_revenue = int(meta[2] or 0)

    # Daily data
    daily_query = f"""
        SELECT date, SUM(cost), SUM(revenue)
        FROM traffic_stats
        WHERE campaign_id = :cid AND date >= :d AND date <= :d_to {source_filter}
        GROUP BY date
        ORDER BY date
    """
    days = get_campaign_daily_days(db, campaign_id, date_from, date_to, source)

    # Last 14 days (fixed window from today)
    last14_to = date.today()
    last14_from = last14_to - timedelta(days=13)
    last14_params = {'cid': campaign_id, 'd': last14_from, 'd_to': last14_to}
    last14_source_filter = _apply_source_filter(last14_params, source)
    last14_row = db.execute(text(f"""
        SELECT SUM(cost), SUM(revenue)
        FROM traffic_stats
        WHERE campaign_id = :cid AND date >= :d AND date <= :d_to {last14_source_filter}
    """), last14_params).fetchone()

    last14_add = db.execute(text("""
        SELECT COALESCE(SUM(revenue), 0)
        FROM additional_monetization
        WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
    """), last14_params).scalar() or 0
    last14_spend = int(last14_row[0] or 0)
    last14_revenue = int(last14_row[1] or 0) + int(last14_add)
    last14_profit = last14_revenue - last14_spend
    last14_roi = round((last14_profit / last14_spend * 100) if last14_spend > 0 else 0)

    return {
        "found": True,
        "campaign_id": campaign_id,
        "campaign": campaign_name,
        "spend": total_spend,
        "days": days,
        "last14": {
            "spend": last14_spend,
            "revenue": last14_revenue,
            "profit": last14_profit,
            "roi": last14_roi,
        },
        "date_from": date_from.strftime('%Y-%m-%d'),
        "date_to": date_to.strftime('%Y-%m-%d'),
    }


@router.get("/metrics/upload-dates")
async def get_upload_dates(db: Session = Depends(get_db)):
    """Проверка какие даты были загружены за последние дни"""
    result = {}
    
    # Traffic stats по датам
    traffic_dates = db.execute(text("""
        SELECT 
            date,
            COUNT(*) as rows,
            COUNT(DISTINCT campaign_id) as campaigns,
            COUNT(DISTINCT traffic_source) as sources
        FROM traffic_stats
        WHERE date >= date('now', '-14 days')
        GROUP BY date
        ORDER BY date DESC
    """)).fetchall()
    
    result['traffic_stats'] = [
        {
            'date': str(row[0]),
            'rows': row[1],
            'campaigns': row[2],
            'sources': row[3]
        }
        for row in traffic_dates
    ]
    
    # Additional monetization по датам
    am_dates = db.execute(text("""
        SELECT 
            date,
            COUNT(*) as rows,
            SUM(revenue) as revenue
        FROM additional_monetization
        WHERE date >= date('now', '-14 days')
        GROUP BY date
        ORDER BY date DESC
    """)).fetchall()
    
    result['additional_monetization'] = [
        {
            'date': str(row[0]),
            'rows': row[1],
            'revenue': float(row[2] or 0)
        }
        for row in am_dates
    ]
    
    # Orphans по датам
    orphan_dates = db.execute(text("""
        SELECT 
            date,
            COUNT(*) as rows,
            SUM(revenue) as revenue
        FROM orphans
        WHERE date >= date('now', '-14 days')
        GROUP BY date
        ORDER BY date DESC
    """)).fetchall()
    
    result['orphans'] = [
        {
            'date': str(row[0]),
            'rows': row[1],
            'revenue': float(row[2] or 0)
        }
        for row in orphan_dates
    ]
    
    return result


@router.get("/metrics/recent-uploads")
async def get_recent_uploads(hours: int = Query(2, description="Hours to look back"), db: Session = Depends(get_db)):
    """Проверка какие файлы загружались за последние N часов по created_at"""
    from datetime import datetime, timedelta
    
    cutoff_time = datetime.now() - timedelta(hours=hours)
    
    # Группируем по created_at (округлённому до минут) и считаем статистику
    uploads = db.execute(text("""
        SELECT 
            strftime('%Y-%m-%d %H:%M', created_at) as upload_time,
            COUNT(*) as rows_inserted,
            COUNT(DISTINCT campaign_id) as campaigns,
            COUNT(DISTINCT traffic_source) as sources,
            MIN(date) as min_date_in_data,
            MAX(date) as max_date_in_data
        FROM traffic_stats
        WHERE created_at >= :cutoff
        GROUP BY strftime('%Y-%m-%d %H:%M', created_at)
        ORDER BY upload_time DESC
    """), {'cutoff': cutoff_time}).fetchall()
    
    result = []
    for row in uploads:
        upload_time, rows, campaigns, sources, min_date, max_date = row
        result.append({
            'upload_time': str(upload_time),
            'rows_inserted': rows,
            'campaigns': campaigns,
            'sources': sources,
            'min_date_in_data': str(min_date) if min_date else None,
            'max_date_in_data': str(max_date) if max_date else None
        })
    
    return {
        'hours_checked': hours,
        'cutoff_time': str(cutoff_time),
        'uploads': result,
        'total_uploads': len(result)
    }
