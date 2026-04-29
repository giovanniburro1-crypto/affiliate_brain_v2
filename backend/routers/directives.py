"""
Advertiser Directives — управление директивами рекламодателей.
STOP / SCALE / BUMP / TEST по token1 + affiliate_network.
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from backend.database import get_db

router = APIRouter()

DIRECTIVES_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS advertiser_directives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token1 VARCHAR(50) NOT NULL,
    affiliate_network VARCHAR(255) NOT NULL,
    action VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(token1, affiliate_network)
)
"""


def _ensure_table(db: Session):
    try:
        engine = db.get_bind()
        with engine.connect() as conn:
            conn.execute(text(DIRECTIVES_CREATE_SQL))
            conn.commit()
    except Exception:
        pass


class DirectiveBody(BaseModel):
    token1: str
    affiliate_network: str
    action: str  # STOP / SCALE / BUMP / TEST


ALLOWED_ACTIONS = ("STOP", "SCALE", "BUMP", "TEST")


@router.get("/directives")
async def list_directives(db: Session = Depends(get_db)):
    """Все директивы."""
    _ensure_table(db)
    rows = db.execute(text(
        "SELECT id, token1, affiliate_network, action, created_at, updated_at "
        "FROM advertiser_directives ORDER BY token1, affiliate_network"
    )).fetchall()
    return {"directives": [
        {
            "id": r[0],
            "token1": r[1],
            "affiliate_network": r[2],
            "action": r[3],
            "created_at": str(r[4]) if r[4] else None,
            "updated_at": str(r[5]) if r[5] else None,
        }
        for r in rows
    ]}


@router.post("/directives")
async def upsert_directive(body: DirectiveBody, db: Session = Depends(get_db)):
    """Создать или обновить директиву (upsert по token1 + affiliate_network)."""
    _ensure_table(db)

    # Нормализация
    token1 = body.token1.strip()
    network = body.affiliate_network.strip()
    action = body.action.strip().upper()

    if not token1 or not network:
        return {"success": False, "error": "Token1 and affiliate network are required"}
    if action not in ALLOWED_ACTIONS:
        return {"success": False, "error": f"Action must be one of: {', '.join(ALLOWED_ACTIONS)}"}

    # Валидация: сеть должна существовать в traffic_stats (только в affiliate_network)
    valid_networks = db.execute(text(
        "SELECT DISTINCT affiliate_network FROM traffic_stats WHERE affiliate_network IS NOT NULL AND affiliate_network != ''"
    )).fetchall()
    
    valid_set = {r[0] for r in valid_networks}
    if network not in valid_set:
        return {"success": False, "error": f"Network '{network}' is not a valid affiliate network from traffic data. Please select from the list."}

    # Upsert: если существует (token1, network) — обновляем action
    existing = db.execute(text(
        "SELECT id FROM advertiser_directives WHERE token1 = :t AND affiliate_network = :n"
    ), {"t": token1, "n": network}).fetchone()

    if existing:
        db.execute(text(
            "UPDATE advertiser_directives SET action = :a, updated_at = :now "
            "WHERE token1 = :t AND affiliate_network = :n"
        ), {"a": action, "t": token1, "n": network, "now": datetime.now()})
    else:
        db.execute(text(
            "INSERT INTO advertiser_directives (token1, affiliate_network, action, created_at, updated_at) "
            "VALUES (:t, :n, :a, :now, :now)"
        ), {"t": token1, "n": network, "a": action, "now": datetime.now()})

    db.commit()
    return {"success": True}


@router.delete("/directives/{directive_id}")
async def delete_directive(directive_id: int, db: Session = Depends(get_db)):
    """Удалить директиву."""
    _ensure_table(db)
    db.execute(text("DELETE FROM advertiser_directives WHERE id = :id"), {"id": directive_id})
    db.commit()
    return {"success": True}


@router.get("/directives/networks")
async def list_networks(q: Optional[str] = None, db: Session = Depends(get_db)):
    """Уникальные affiliate_network из traffic_stats."""
    if q and q.strip():
        rows = db.execute(text(
            "SELECT DISTINCT affiliate_network FROM traffic_stats "
            "WHERE affiliate_network IS NOT NULL AND affiliate_network != '' AND LOWER(affiliate_network) LIKE :q "
            "ORDER BY affiliate_network LIMIT 50"
        ), {"q": f"%{q.strip().lower()}%"}).fetchall()
    else:
        rows = db.execute(text(
            "SELECT DISTINCT affiliate_network FROM traffic_stats "
            "WHERE affiliate_network IS NOT NULL AND affiliate_network != '' "
            "ORDER BY affiliate_network LIMIT 100"
        )).fetchall()
    return {"networks": [r[0] for r in rows]}


@router.get("/directives/by-campaigns")
async def directives_by_campaigns(db: Session = Depends(get_db)):
    """
    Все директивы, сгруппированные по token1.
    Используется на Dashboard для tooltip при наведении на кампанию.
    Возвращает: { "2090": [{"network": "A225", "action": "STOP"}, ...], ... }
    """
    _ensure_table(db)
    rows = db.execute(text(
        "SELECT token1, affiliate_network, action FROM advertiser_directives "
        "ORDER BY token1, affiliate_network"
    )).fetchall()

    grouped = {}
    for r in rows:
        t1 = r[0]
        if t1 not in grouped:
            grouped[t1] = []
        grouped[t1].append({"network": r[1], "action": r[2]})

    return {"directives": grouped}
