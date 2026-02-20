from datetime import date, timedelta
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.database import get_db

router = APIRouter()

# Исключаем из трафика источники с доп. монетизацией (не только 'AddMonetisation', но и любые со словом monetisation)
FILTER_OUT_MONETISATION = "AND traffic_source != 'AddMonetisation' AND LOWER(traffic_source) NOT LIKE '%monetisation%'"


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
    """Единый расчёт тоталов: spend, base_revenue, add_mon, total_profit. Без AS в SELECT — порядок колонок: 0=cost, 1=revenue, 2=conversions, 3=clicks."""
    source_filter = "AND traffic_source = :source" if source and source != 'all' else FILTER_OUT_MONETISATION
    params = {'date_from': date_from, 'date_to': date_to}
    if source and source != 'all':
        params['source'] = source
    r = db.execute(text(
        f"SELECT COALESCE(SUM(cost),0), COALESCE(SUM(revenue),0), COALESCE(SUM(conversions),0), COUNT(*) "
        f"FROM traffic_stats WHERE date >= :date_from AND date <= :date_to AND traffic_source IS NOT NULL {source_filter}"
    ), params).fetchone()
    total_spend = int(round(float(r[0] or 0)))
    total_base_revenue = int(round(float(r[1] or 0)))
    conversions = int(r[2] or 0)
    clicks = int(r[3] or 0)

    if source and source != 'all':
        add_mon = db.execute(text("""
            SELECT COALESCE(SUM(am.revenue), 0)
            FROM additional_monetization am
            WHERE am.date >= :date_from AND am.date <= :date_to
              AND am.campaign_id IN (SELECT DISTINCT campaign_id FROM traffic_stats WHERE traffic_source = :source)
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
    source_filter = "AND traffic_source = :source" if source and source != 'all' else ""
    having = " HAVING SUM(cost) >= :min_cost" if min_cost > 0 else ""
    limit_val = 500 if min_cost > 0 else 50
    query = text(
        f"SELECT campaign_id, campaign, traffic_source, SUM(cost), SUM(revenue), SUM(conversions), COUNT(*) "
        f"FROM traffic_stats WHERE date >= :date_from AND date <= :date_to {source_filter} "
        f"GROUP BY campaign_id, campaign, traffic_source{having} ORDER BY SUM(revenue)-SUM(cost) DESC LIMIT {limit_val}"
    )
    params = {'date_from': date_from, 'date_to': date_to}
    if source and source != 'all':
        params['source'] = source
    if min_cost > 0:
        params['min_cost'] = min_cost
    rows = db.execute(query, params).fetchall()
    campaigns = []
    for row in rows:
        spend, revenue = int(row[3] or 0), int(row[4] or 0)
        profit = revenue - spend
        roi = round((profit / spend * 100) if spend > 0 else 0)
        campaigns.append({"campaign_id": row[0], "campaign": row[1], "source": row[2], "spend": spend, "revenue": revenue, "profit": profit, "roi": roi, "conversions": int(row[5] or 0), "clicks": int(row[6] or 0)})
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
async def get_sources(db: Session = Depends(get_db)):
    result = db.execute(text(
        f"SELECT DISTINCT traffic_source FROM traffic_stats WHERE traffic_source IS NOT NULL {FILTER_OUT_MONETISATION} ORDER BY traffic_source"
    )).fetchall()
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
    today = date_to
    source_filter = "AND traffic_source = :source" if source and source != "all" else FILTER_OUT_MONETISATION
    params = {"d": date_from, "d_to": date_to}
    if source and source != "all":
        params["source"] = source
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
    by_date = {row[0]: {"cost": int(row[1] or 0), "revenue": int(row[2] or 0), "conversions": int(row[3] or 0), "clicks": int(row[4] or 0)} for row in rows}
    daily = []
    days_count = (date_to - date_from).days + 1
    for i in range(days_count):
        d = date_from + timedelta(days=i)
        rec = by_date.get(d, {"cost": 0, "revenue": 0, "conversions": 0, "clicks": 0})
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
        f"SELECT DISTINCT traffic_source FROM traffic_stats WHERE date >= :d AND date <= :d_to AND traffic_source IS NOT NULL {FILTER_OUT_MONETISATION}"
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

    source_filter = "AND traffic_source = :source" if source and source != 'all' else FILTER_OUT_MONETISATION
    params = {'date_from': date_from, 'date_to': date_to}
    if source and source != 'all':
        params['source'] = source

    # OS: один запрос, читаем по именам колонок (cost_sum, revenue_sum), чтобы не зависеть от порядка
    os_raw = db.execute(text(f"""
        SELECT COALESCE(os, 'Unknown'), COUNT(*), SUM(cost), SUM(revenue)
        FROM traffic_stats WHERE date >= :date_from AND date <= :date_to AND traffic_source IS NOT NULL {source_filter}
        GROUP BY COALESCE(os, 'Unknown')
    """), params).fetchall()

    total_os_clicks = sum(int(row[1] or 0) for row in os_raw)
    os_base_revenue_sum = sum(int(round(float(row[3] or 0))) for row in os_raw)
    if os_base_revenue_sum == 0:
        os_base_revenue_sum = 1

    # Только 3 строки: Android, Other, iOS. Unknown считаем как Other.
    os_groups = {"Android": {"clicks": 0, "profit": 0}, "Other": {"clicks": 0, "profit": 0}, "iOS": {"clicks": 0, "profit": 0}}
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
        else:
            # Unknown и любые другие → Other
            os_groups["Other"]["clicks"] += clicks
            os_groups["Other"]["profit"] += profit_os

    os_result = []
    for name in ["Android", "Other", "iOS"]:
        data = os_groups[name]
        traffic_pct = round(data["clicks"] / total_os_clicks * 100) if total_os_clicks > 0 else 0
        profit_pct = round(data["profit"] / total_profit * 100) if total_profit != 0 else 0
        profit_pct = max(-9999, min(9999, profit_pct))
        os_result.append({"name": name, "clicks": data["clicks"], "traffic_pct": traffic_pct, "profit": data["profit"], "profit_pct": profit_pct})

    # Device: порядок колонок 0=device_name, 1=clicks, 2=cost_sum, 3=revenue_sum — читаем по индексу
    device_raw = db.execute(text(f"""
        SELECT COALESCE(device_type, 'Unknown'), COUNT(*), SUM(cost), SUM(revenue)
        FROM traffic_stats WHERE date >= :date_from AND date <= :date_to AND traffic_source IS NOT NULL {source_filter}
        GROUP BY COALESCE(device_type, 'Unknown')
    """), params).fetchall()

    total_dev_clicks = sum(int(row[1] or 0) for row in device_raw)
    dev_base_revenue_sum = sum(int(round(float(row[3] or 0))) for row in device_raw)
    if dev_base_revenue_sum == 0:
        dev_base_revenue_sum = 1

    # Только 3 строки: Mobile, Desktop, Other. Unknown считаем как Other.
    device_groups = {"Mobile": {"clicks": 0, "profit": 0}, "Desktop": {"clicks": 0, "profit": 0}, "Other": {"clicks": 0, "profit": 0}}
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
        else:
            # Unknown и любые другие → Other
            device_groups["Other"]["clicks"] += clicks
            device_groups["Other"]["profit"] += profit_dev

    device_result = []
    for name in ["Mobile", "Desktop", "Other"]:
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
async def get_traffic_sources_summary(
    period: int = Query(14),
    date_from_param: Optional[str] = Query(None, alias="date_from"),
    date_to_param: Optional[str] = Query(None, alias="date_to"),
    source: Optional[str] = None,
    db: Session = Depends(get_db),
):
    date_from, date_to = _period_or_range(period, date_from_param, date_to_param)
    source_filter = "AND traffic_source = :source" if source and source != "all" else ""
    params = {'d': date_from, 'd_to': date_to}
    if source and source != "all":
        params['source'] = source

    # additional_monetization за период (при выборе источника — только кампании этого источника)
    if source and source != "all":
        total_add = float(db.execute(text("""
            SELECT COALESCE(SUM(am.revenue), 0)
            FROM additional_monetization am
            WHERE am.date >= :d AND am.date <= :d_to
              AND am.campaign_id IN (SELECT DISTINCT campaign_id FROM traffic_stats WHERE traffic_source = :source)
        """), params).scalar() or 0)
    else:
        total_add = float(db.execute(text(
            "SELECT COALESCE(SUM(revenue),0) FROM additional_monetization WHERE date >= :d AND date <= :d_to"
        ), params).scalar() or 0)

    # Получаем данные по traffic sources из traffic_stats (с учётом выбранного источника)
    sources = db.execute(text(f"""
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
    
    # Считаем общий базовый revenue для пропорций
    total_base_revenue = sum(float(row[2] or 0) for row in sources)
    
    result = []
    for row in sources:
        source_name = row[0]
        spend = int(row[1] or 0)
        base_revenue = float(row[2] or 0)
        
        # Распределяем additional_monetization пропорционально базовому revenue
        if total_base_revenue > 0:
            add_share = int(total_add * (base_revenue / total_base_revenue))
        else:
            add_share = 0
        
        total_revenue = int(base_revenue) + add_share
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
    source_filter = "AND traffic_source = :source" if source and source != "all" else ""
    params = {'d': date_from, 'd_to': date_to}
    if source and source != "all":
        params['source'] = source

    # Получаем топ-25 кампаний по spend (с учётом выбранного источника)
    campaigns_query = f"""
        SELECT campaign_id, campaign, SUM(cost) as total_spend
        FROM traffic_stats 
        WHERE date >= :d AND date <= :d_to AND campaign_id IS NOT NULL {source_filter}
        GROUP BY campaign_id, campaign
        ORDER BY total_spend DESC
        LIMIT 25
    """
    campaigns = db.execute(text(campaigns_query), params).fetchall()

    result = []
    for row in campaigns:
        campaign_id = row[0]
        campaign_name = row[1]
        total_spend = int(row[2] or 0)
        day_params = {'cid': campaign_id, 'd': date_from, 'd_to': date_to}
        if source and source != "all":
            day_params['source'] = source

        # Получаем данные по дням для этой кампании (с учётом источника)
        daily_query = f"""
            SELECT date, SUM(cost), SUM(revenue)
            FROM traffic_stats 
            WHERE campaign_id = :cid AND date >= :d AND date <= :d_to {source_filter}
            GROUP BY date
            ORDER BY date
        """
        daily = db.execute(text(daily_query), day_params).fetchall()
        
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


def get_campaign_daily_days(
    db: Session,
    campaign_id: str,
    date_from: date,
    date_to: date,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Возвращает days[MM-DD] = {profit, color} для внутреннего использования."""
    source_filter = "AND traffic_source = :source" if source and source != "all" else ""
    params = {'cid': campaign_id, 'd': date_from, 'd_to': date_to}
    if source and source != "all":
        params['source'] = source
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
        day_date = day_row[0].strftime('%m-%d')
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
    source_filter = "AND traffic_source = :source" if source and source != "all" else ""
    params = {'cid': campaign_id, 'd': date_from, 'd_to': date_to}
    if source and source != "all":
        params['source'] = source

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
    if source and source != "all":
        last14_params['source'] = source
    last14_row = db.execute(text(f"""
        SELECT SUM(cost), SUM(revenue)
        FROM traffic_stats
        WHERE campaign_id = :cid AND date >= :d AND date <= :d_to {source_filter}
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
        WHERE date >= CURRENT_DATE - INTERVAL '14 days'
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
        WHERE date >= CURRENT_DATE - INTERVAL '14 days'
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
        WHERE date >= CURRENT_DATE - INTERVAL '14 days'
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
            DATE_TRUNC('minute', created_at) as upload_time,
            COUNT(*) as rows_inserted,
            COUNT(DISTINCT campaign_id) as campaigns,
            COUNT(DISTINCT traffic_source) as sources,
            MIN(date) as min_date_in_data,
            MAX(date) as max_date_in_data
        FROM traffic_stats
        WHERE created_at >= :cutoff
        GROUP BY DATE_TRUNC('minute', created_at)
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
