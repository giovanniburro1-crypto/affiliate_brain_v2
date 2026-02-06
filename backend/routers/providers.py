from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
import json
from pathlib import Path
from typing import Optional

router = APIRouter()


class TestProviderRequest(BaseModel):
    provider: str
    api_key: str
    base_url: Optional[str] = None


CONFIG_PATH = Path("providers_config.json")


@router.post("/providers/test")
async def test_provider(req: TestProviderRequest):
    """
    Тестирует ключ и возвращает список моделей.
    Для известных провайдеров делает реальный запрос к API.
    Для кастомных использует base_url, который приходит из фронта.
    """
    if not req.api_key.strip():
        return {"success": False, "error": "Empty API key"}

    provider = req.provider.lower()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Groq
            if provider == "groq":
                res = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {req.api_key}"},
                )
                if res.status_code != 200:
                    return {"success": False, "error": f"Groq: {res.status_code}"}
                data = res.json()
                models = [{"id": m["id"], "name": m["id"]} for m in data.get("data", [])]
                return {"success": True, "models": models}

            # OpenRouter
            if provider == "openrouter":
                res = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {req.api_key}"},
                )
                if res.status_code != 200:
                    return {"success": False, "error": f"OpenRouter: {res.status_code}"}
                data = res.json()
                models = [
                    {"id": m["id"], "name": m.get("name", m["id"])}
                    for m in data.get("data", [])
                ]
                return {"success": True, "models": models}

            # DeepSeek (OpenAI совместимый)
            if provider == "deepseek":
                res = await client.get(
                    "https://api.deepseek.com/v1/models",
                    headers={"Authorization": f"Bearer {req.api_key}"},
                )
                if res.status_code != 200:
                    return {"success": False, "error": f"DeepSeek: {res.status_code}"}
                data = res.json()
                models = [{"id": m["id"], "name": m["id"]} for m in data.get("data", [])]
                return {"success": True, "models": models}

            # Google Gemini
            if provider == "google":
                if not req.base_url:
                    # По-умолчанию официальный endpoint
                    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={req.api_key}"
                else:
                    url = f"{req.base_url}"
                res = await client.get(url)
                if res.status_code != 200:
                    return {"success": False, "error": f"Google: {res.status_code}"}
                data = res.json()
                models = [
                    {
                        "id": m["name"].split("/")[-1],
                        "name": m.get("displayName", m["name"]),
                    }
                    for m in data.get("models", [])
                ]
                return {"success": True, "models": models}

            # Кастомный провайдер: нужен base_url
            if req.base_url:
                res = await client.get(
                    req.base_url,
                    headers={"Authorization": f"Bearer {req.api_key}"},
                )
                if res.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Custom provider: {res.status_code}",
                    }
                data = res.json()
                # Пытаемся понять формат: OpenAI-like (data), или просто массив моделей
                if isinstance(data, dict) and "data" in data:
                    raw_models = data["data"]
                elif isinstance(data, list):
                    raw_models = data
                else:
                    raw_models = []

                models = []
                for m in raw_models:
                    mid = m.get("id") or m.get("name")
                    if not mid:
                        continue
                    mname = m.get("name") or mid
                    models.append({"id": mid, "name": mname})

                return {"success": True, "models": models}

            return {"success": False, "error": f"Unknown provider: {req.provider}"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/providers/save")
async def save_providers(data: dict):
    """
    Сохраняем ключи и выбранные модели в локальный JSON-файл providers_config.json.
    Формат:
    {
      "groq": { "key": "...", "models": [...], "base_url": null },
      "myprovider": { "key": "...", "models": [...], "base_url": "https://..." }
    }
    """
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")

    try:
        existing: dict = {}
        if CONFIG_PATH.exists():
            existing = json.loads(CONFIG_PATH.read_text())

        # Обновляем / добавляем провайдеров
        for provider, cfg in data.items():
            if not isinstance(cfg, dict):
                continue
            key = cfg.get("key", "")
            models = cfg.get("models", [])
            base_url = cfg.get("base_url")
            existing[provider] = {
                "key": key,
                "models": models,
                "base_url": base_url,
            }

        CONFIG_PATH.write_text(json.dumps(existing, indent=2))
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

