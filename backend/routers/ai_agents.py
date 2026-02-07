from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.database import get_db
from pydantic import BaseModel
from typing import Optional
import httpx
import json

router = APIRouter()

class AgentConfig(BaseModel):
    agent_name: str
    enabled: bool
    provider: str
    model: str
    system_prompt: str

class TestRequest(BaseModel):
    provider: str
    model: str
    system_prompt: str
    campaign_data: dict

@router.get("/agents")
async def get_agents(db: Session = Depends(get_db)):
    """Получить все агенты"""
    agents = db.execute(text("""
        SELECT id, agent_name, enabled, provider, model, system_prompt
        FROM ai_agents
        ORDER BY id
    """)).fetchall()
    
    return {"agents": [
        {
            "id": a[0],
            "agent_name": a[1],
            "enabled": a[2],
            "provider": a[3],
            "model": a[4],
            "system_prompt": a[5]
        } for a in agents
    ]}

@router.put("/agents/{agent_name}")
async def update_agent(agent_name: str, config: AgentConfig, db: Session = Depends(get_db)):
    """Обновить конфиг агента"""
    db.execute(text("""
        UPDATE ai_agents
        SET enabled = :enabled,
            provider = :provider,
            model = :model,
            system_prompt = :prompt,
            updated_at = NOW()
        WHERE agent_name = :name
    """), {
        'enabled': config.enabled,
        'provider': config.provider,
        'model': config.model,
        'prompt': config.system_prompt,
        'name': agent_name
    })
    db.commit()
    return {"success": True}

@router.post("/agents/test")
async def test_agent(req: TestRequest):
    """Тестировать агента с реальным API"""
    try:
        # Формируем промпт с данными кампании
        user_message = f"""Campaign data:
{json.dumps(req.campaign_data, indent=2)}

Analyze this campaign and provide recommendations."""

        # Вызываем API провайдера
        if req.provider == 'groq':
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    'https://api.groq.com/openai/v1/chat/completions',
                    headers={'Authorization': f'Bearer {get_groq_key()}'},
                    json={
                        'model': req.model,
                        'messages': [
                            {'role': 'system', 'content': req.system_prompt},
                            {'role': 'user', 'content': user_message}
                        ],
                        'max_tokens': 500
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {"success": True, "response": data['choices'][0]['message']['content']}
                else:
                    return {"success": False, "error": f"API returned {response.status_code}"}
        
        # Другие провайдеры добавим позже
        return {"success": False, "error": "Provider not implemented yet"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_groq_key():
    """Временно возвращаем пустую строку, потом добавим из .env"""
    return ""
