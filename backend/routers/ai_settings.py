import json
from sqlalchemy.orm import Session
from backend.database import get_db
from sqlalchemy import text
from pathlib import Path
from typing import Dict
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter()
CONFIG_FILE = Path("config/ai_roles_config.json")

class RoleConfig(BaseModel):
    role: str
    provider: str
    model: str
    prompt: str
    enabled: bool = True

class TestRequest(BaseModel):
    role: str
    provider: str
    model: str
    prompt: str
    campaign_data: Dict

@router.get("/configs")
async def get_configs():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f: return json.load(f)
    return {}

@router.post("/save")
async def save_config(config: RoleConfig):
    configs = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f: configs = json.load(f)
    configs[config.role] = {"provider": config.provider, "model": config.model, "prompt": config.prompt, "enabled": config.enabled}
    CONFIG_FILE.parent.mkdir(exist_ok=True)
    with open(CONFIG_FILE, 'w') as f: json.dump(configs, f, indent=2)
    return {"success": True}

@router.post("/test")
async def test_role(req: TestRequest):
    return {"success": True, "response": {"role": req.role, "verdict": "HOLD", "confidence": 75, "reasoning": f"ROI {req.campaign_data.get('roi', 0)}%"}}

import subprocess

@router.post("/git/commit")
async def git_commit(data: dict):
    try:
        message = data.get('message', 'Auto backup')
        cwd = '/Users/andreylp/affiliate_brain/app'
        
        # Stage all changes in app/
        subprocess.run(['git', 'add', '-A'], cwd=cwd, check=True)
        
        # Commit (returns non-zero if no changes, so we capture output instead of check=True)
        commit_res = subprocess.run(['git', 'commit', '-m', message], cwd=cwd, capture_output=True, text=True)
        
        # Push to origin main
        push_res = subprocess.run(['git', 'push', 'origin', 'main'], cwd=cwd, capture_output=True, text=True)
        
        if push_res.returncode != 0:
            return {"success": False, "error": push_res.stderr or push_res.stdout}
            
        return {"success": True, "message": "Pushed to GitHub!"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/database/info")
async def get_db_info():
    """Возвращает информацию о размере БД"""
    import os
    db_path = "/Users/andreylp/affiliate_brain/database.db"
    if os.path.exists(db_path):
        size_bytes = os.path.getsize(db_path)
        size_mb = round(size_bytes / (1024 * 1024), 2)
        return {"success": True, "size_mb": size_mb, "path": db_path}
    return {"success": False, "error": "Database file not found"}

@router.post("/database/clear")
async def clear_database(data: dict = None, db: Session = Depends(get_db)):
    """Очистка данных из БД (опционально за период)"""
    try:
        date_from = data.get('date_from') if data else None
        date_to = data.get('date_to') if data else None
        
        where_clause = ""
        params = {}
        if date_from and date_to:
            where_clause = " WHERE date >= :d_from AND date <= :d_to"
            params = {"d_from": date_from, "d_to": date_to}
        
        # В SQLite используем DELETE FROM вместо TRUNCATE
        db.execute(text(f"DELETE FROM traffic_stats{where_clause}"), params)
        db.execute(text(f"DELETE FROM additional_monetization{where_clause}"), params)
        db.execute(text(f"DELETE FROM orphans{where_clause}"), params)
        
        # Если это полная очистка (без дат), чистим и другие таблицы
        if not where_clause:
            try:
                db.execute(text("DELETE FROM recheck_queue"))
            except: pass
            
            db.commit()
            
            # Используем полностью независимое подключение для VACUUM
            # чтобы не сломать пул соединений SQLAlchemy
            import sqlite3
            import os
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "database.db")
            if os.path.exists(db_path):
                try:
                    conn = sqlite3.connect(db_path, isolation_level=None)
                    conn.execute("VACUUM")
                    conn.close()
                except: pass
            
            return {"success": True, "message": "Database fully reset and optimized (VACUUM)"}
            
        db.commit()
        return {"success": True, "message": "Data cleared successfully"}
    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
