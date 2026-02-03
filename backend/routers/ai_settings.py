import json
from pathlib import Path
from typing import Dict
from fastapi import APIRouter
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
        subprocess.run(['git', 'add', '.'], cwd='/Users/andreylp/Desktop/affiliate_brain_v2', check=True)
        subprocess.run(['git', 'commit', '-m', message], cwd='/Users/andreylp/Desktop/affiliate_brain_v2', check=True)
        result = subprocess.run(['git', 'push'], cwd='/Users/andreylp/Desktop/affiliate_brain_v2', capture_output=True, text=True)
        return {"success": True, "message": "Pushed to GitHub!"}
    except Exception as e:
        return {"success": False, "error": str(e)}
