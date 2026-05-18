from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.database import get_db
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import httpx
import json
from datetime import datetime

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
    category: str = "top5"

class TestRequest(BaseModel):
    provider: str
    model: str
    system_prompt: str
    campaign_data: dict


class CouncilRequest(BaseModel):
    campaign_id: str
    period: int = 14
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    category: str = "top5"

@router.get("/agents")
async def get_agents(category: str = "top5", db: Session = Depends(get_db)):
    """Получить агенты по категории"""
    agents = db.execute(text("""
        SELECT id, agent_name, enabled, provider, model, system_prompt, category
        FROM ai_agents
        WHERE category = :category
        ORDER BY id
    """), {"category": category}).fetchall()
    
    return {"agents": [
        {
            "id": a[0],
            "agent_name": a[1],
            "enabled": a[2],
            "provider": a[3],
            "model": a[4],
            "system_prompt": a[5],
            "category": a[6]
        } for a in agents
    ]}

@router.put("/agents/{agent_name}")
async def update_agent(agent_name: str, config: AgentConfig, db: Session = Depends(get_db)):
    """Обновить или создать конфиг агента"""
    # Сначала проверим существование
    existing = db.execute(text("SELECT id FROM ai_agents WHERE agent_name = :name"), {"name": agent_name}).fetchone()
    
    if existing:
        db.execute(text("""
            UPDATE ai_agents
            SET enabled = :enabled,
                provider = :provider,
                model = :model,
                system_prompt = :prompt,
                category = :category,
                updated_at = :now
            WHERE agent_name = :name
        """), {
            'enabled': config.enabled,
            'provider': config.provider,
            'model': config.model,
            'prompt': config.system_prompt,
            'category': config.category,
            'name': agent_name,
            'now': datetime.now()
        })
    else:
        db.execute(text("""
            INSERT INTO ai_agents (agent_name, enabled, provider, model, system_prompt, category, updated_at)
            VALUES (:name, :enabled, :provider, :model, :prompt, :category, :now)
        """), {
            'name': agent_name,
            'enabled': config.enabled,
            'provider': config.provider,
            'model': config.model,
            'prompt': config.system_prompt,
            'category': config.category,
            'now': datetime.now()
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


def _build_user_message(campaign_data: dict) -> str:
    data = campaign_data or {}
    has_breakdown = "by_token2" in data or "top_combinations_token2_offer_id_jump" in data or "by_offer_id" in data
    if has_breakdown:
        hint = """
Use ONLY the numbers from this data; do not invent EPC, CR, or percentages.
Field mapping (column_labels): token2 = Token 2 (creative), offer_id = Offer ID, lander_id = Lander ID (jump), os = OS, country = Country, device_type = Device Type. Value "(empty)" = no value in DB for that dimension.
Связка = one source combination, e.g. token2 + offer_id + lander_id OR os + offer_id + lander_id. Give ONE short non-obvious insight (if the whole campaign is US Android, do not say "US Android works"; find a less obvious winning combo)."""
    else:
        hint = ""
    return f"""Campaign data (real numbers from database):
{json.dumps(data, indent=2)}
{hint}

Analyze this campaign and provide recommendations."""


async def _run_one_agent(client: httpx.AsyncClient, agent: dict, campaign_data: dict) -> tuple[str, str]:
    """Вызов одного агента. Возвращает (response_text, error). error пустой при успехе."""
    user_message = _build_user_message(campaign_data)
    provider = (agent.get("provider") or "").lower()
    model = agent.get("model") or ""
    system_prompt = agent.get("system_prompt") or ""
    cfg = _get_provider_config(provider)
    api_key = cfg.get("key") or ""
    if not api_key:
        return "", f"API key for '{provider}' not found. Add it in Settings → Connect Models."

    if provider == "groq":
        ok, out = await _chat_openai_compatible(
            client, "https://api.groq.com/openai/v1/chat/completions",
            api_key, model, system_prompt, user_message
        )
        return (out, "") if ok else ("", out)
    if provider == "openrouter":
        ok, out = await _chat_openai_compatible(
            client, "https://openrouter.ai/api/v1/chat/completions",
            api_key, model, system_prompt, user_message
        )
        return (out, "") if ok else ("", out)
    if provider == "deepseek":
        ok, out = await _chat_openai_compatible(
            client, "https://api.deepseek.com/v1/chat/completions",
            api_key, model, system_prompt, user_message
        )
        return (out, "") if ok else ("", out)
    if provider == "google":
        model_name = (model or "").strip().replace("models/", "")
        if not model_name:
            return "", "Model name is required for Google"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        full_prompt = f"{system_prompt}\n\nUser:\n{user_message}"
        body = {"contents": [{"parts": [{"text": full_prompt}]}], "generationConfig": {"maxOutputTokens": 500}}
        try:
            response = await client.post(url, json=body, timeout=30.0)
            if response.status_code != 200:
                return "", f"API returned {response.status_code}: {response.text[:200]}"
            data = response.json()
            parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            text_out = (parts[0].get("text", "") if parts else "").strip()
            return (text_out or "(empty)", "")
        except Exception as e:
            return "", str(e)
    base_url = (cfg.get("base_url") or "").strip().rstrip("/")
    if base_url:
        chat_url = base_url if "chat" in base_url else f"{base_url}/chat/completions"
        ok, out = await _chat_openai_compatible(
            client, chat_url, api_key, model, system_prompt, user_message
        )
        return (out, "") if ok else ("", out)
    return "", f"Unknown provider: {provider}"


@router.post("/agents/council")
async def council(req: CouncilRequest, request: Request, db: Session = Depends(get_db)):
    """Запустить все включённые AI-агенты по кампании и вернуть ответы (для правой панели TOP-5)."""
    try:
        agents_rows = db.execute(text("""
            SELECT agent_name, enabled, provider, model, system_prompt
            FROM ai_agents 
            WHERE enabled = true AND category = :category
            ORDER BY id
        """), {"category": req.category}).fetchall()
        agents = [
            {"agent_name": r[0], "enabled": True, "provider": r[2], "model": r[3], "system_prompt": r[4]}
            for r in agents_rows
        ]
        if not agents:
            return {"success": False, "error": "Нет включённых агентов. Включите агентов в Settings."}

        base_url = str(request.base_url).rstrip("/")
        params = {"campaign_id": req.campaign_id}
        if req.date_from and req.date_to:
            params["date_from"] = req.date_from
            params["date_to"] = req.date_to
        else:
            params["period"] = req.period
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            br = await http_client.get(
                f"{base_url}/api/metrics/campaign-breakdown",
                params=params,
            )
            if br.status_code != 200:
                return {"success": False, "error": "Не удалось загрузить разбивку кампании."}
            campaign_data = br.json()

        results = []
        async with httpx.AsyncClient(timeout=35.0) as client:
            for agent in agents:
                response_text, error = await _run_one_agent(client, agent, campaign_data)
                results.append({
                    "agent_name": agent["agent_name"],
                    "response": response_text if not error else None,
                    "error": error or None,
                })
        return {"success": True, "results": results}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/agents/test")
async def test_agent(req: TestRequest):
    """Тестировать агента с реальным API. Ключи берутся из Connect Models (providers_config.json)."""
    try:
        user_message = _build_user_message(req.campaign_data or {})

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
