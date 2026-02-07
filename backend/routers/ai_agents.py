from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.database import get_db
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import httpx
import json

router = APIRouter()
PROVIDERS_CONFIG_PATH = Path("providers_config.json")


def _get_provider_config(provider: str) -> dict:
    """Читает ключ и base_url провайдера из providers_config.json (Connect Models)."""
    if not PROVIDERS_CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(PROVIDERS_CONFIG_PATH.read_text())
        cfg = data.get((provider or "").lower(), {})
        return {"key": (cfg.get("key") or "").strip(), "base_url": cfg.get("base_url")}
    except Exception:
        return {}

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

async def _chat_openai_compatible(client: httpx.AsyncClient, url: str, api_key: str, model: str, system_prompt: str, user_message: str) -> tuple[bool, str]:
    """Общий вызов для Groq, OpenRouter, DeepSeek (OpenAI-совместимый chat/completions)."""
    response = await client.post(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 500,
        },
        timeout=30.0,
    )
    if response.status_code != 200:
        return False, f"API returned {response.status_code}: {response.text[:200]}"
    data = response.json()
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return True, content


@router.post("/agents/test")
async def test_agent(req: TestRequest):
    """Тестировать агента с реальным API. Ключи берутся из Connect Models (providers_config.json)."""
    try:
        data = req.campaign_data or {}
        has_breakdown = "by_token2" in data or "top_combinations_token2_offer_id_jump" in data or "by_offer_id" in data
        if has_breakdown:
            hint = """
Use ONLY the numbers from this data; do not invent EPC, CR, or percentages.
Field mapping (column_labels): token2 = Token 2 (creative), offer_id = Offer ID, lander_id = Lander ID (jump), os = OS, country = Country, device_type = Device Type. Value "(empty)" = no value in DB for that dimension.
Связка = one source combination, e.g. token2 + offer_id + lander_id OR os + offer_id + lander_id. Give ONE short non-obvious insight (if the whole campaign is US Android, do not say "US Android works"; find a less obvious winning combo)."""
        else:
            hint = ""
        user_message = f"""Campaign data (real numbers from database):
{json.dumps(data, indent=2)}
{hint}

Analyze this campaign and provide recommendations."""

        cfg = _get_provider_config(req.provider)
        api_key = cfg.get("key") or ""
        if not api_key:
            return {"success": False, "error": f"API key for provider '{req.provider}' not found. Add it in Settings → Connect Models."}

        provider = (req.provider or "").lower()
        async with httpx.AsyncClient() as client:
            # Groq
            if provider == "groq":
                ok, out = await _chat_openai_compatible(
                    client, "https://api.groq.com/openai/v1/chat/completions",
                    api_key, req.model, req.system_prompt, user_message
                )
                return {"success": ok, "response": out} if ok else {"success": False, "error": out}

            # OpenRouter
            if provider == "openrouter":
                ok, out = await _chat_openai_compatible(
                    client, "https://openrouter.ai/api/v1/chat/completions",
                    api_key, req.model, req.system_prompt, user_message
                )
                return {"success": ok, "response": out} if ok else {"success": False, "error": out}

            # DeepSeek (OpenAI-совместимый)
            if provider == "deepseek":
                ok, out = await _chat_openai_compatible(
                    client, "https://api.deepseek.com/v1/chat/completions",
                    api_key, req.model, req.system_prompt, user_message
                )
                return {"success": ok, "response": out} if ok else {"success": False, "error": out}

            # Google Gemini (другой API: generateContent)
            if provider == "google":
                model_name = (req.model or "").strip().replace("models/", "")
                if not model_name:
                    return {"success": False, "error": "Model name is required for Google"}
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                full_prompt = f"{req.system_prompt}\n\nUser:\n{user_message}"
                body = {"contents": [{"parts": [{"text": full_prompt}]}], "generationConfig": {"maxOutputTokens": 500}}
                response = await client.post(url, json=body, timeout=30.0)
                if response.status_code != 200:
                    return {"success": False, "error": f"API returned {response.status_code}: {response.text[:200]}"}
                data = response.json()
                parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
                text_out = (parts[0].get("text", "") if parts else "").strip()
                return {"success": True, "response": text_out or "(empty)"}

            # Кастомный провайдер: base_url должен быть URL chat/completions
            base_url = (cfg.get("base_url") or "").strip().rstrip("/")
            if base_url:
                chat_url = base_url if "chat" in base_url else f"{base_url}/chat/completions"
                ok, out = await _chat_openai_compatible(
                    client, chat_url, api_key, req.model, req.system_prompt, user_message
                )
                return {"success": ok, "response": out} if ok else {"success": False, "error": out}

            return {"success": False, "error": f"Unknown provider: {req.provider}"}

    except Exception as e:
        return {"success": False, "error": str(e)}
