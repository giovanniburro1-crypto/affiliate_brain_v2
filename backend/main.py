from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response
import uvicorn
from backend.config import settings
from backend.database import check_db_connection
from backend.routers import upload_router, metrics_router, bot_agent_router, ai_settings_router, providers, ai_agents, company_analytics_router, insight_config_router, directives_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting Affiliate Brain v2.0...")
    print("✅ DB:", "OK" if check_db_connection() else "FAIL")
    yield
    print("👋 Bye!")

app = FastAPI(title="Affiliate Brain v2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/assets", StaticFiles(directory="frontend/assets"), name="assets")

app.include_router(upload_router, prefix="/api", tags=["Upload"])
app.include_router(metrics_router, prefix="/api", tags=["Metrics"])
app.include_router(bot_agent_router, prefix="/api/bot-agent", tags=["Bot Agent"])
app.include_router(ai_settings_router, prefix="/api/ai-settings", tags=["AI Settings"])
app.include_router(providers.router, prefix="/api", tags=["Providers"])
app.include_router(ai_agents.router, prefix="/api", tags=["AI Agents"])
app.include_router(company_analytics_router, prefix="/api", tags=["Company Analytics"])
app.include_router(insight_config_router.router, prefix="/api/settings", tags=["Insight Settings"])
app.include_router(directives_router, prefix="/api", tags=["Directives"])

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    with open("frontend/index.html") as f: return f.read()

@app.get("/top5", response_class=HTMLResponse)
async def top5():
    with open("frontend/top5.html") as f: return f.read()

@app.get("/bot-top5", response_class=HTMLResponse)
async def bot_top5():
    with open("frontend/bot-top5.html") as f: return f.read()

@app.get("/bot-stop-optimize", response_class=HTMLResponse)
async def bot_stop_optimize():
    with open("frontend/bot-stop-optimize.html") as f: return f.read()

@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
    with open("frontend/settings.html") as f: return f.read()

@app.get("/general-settings", response_class=HTMLResponse)
async def general_settings():
    with open("frontend/general-settings.html") as f: return f.read()

@app.get("/ai-top5", response_class=HTMLResponse)
async def ai_top5():
    with open("frontend/ai-top5.html") as f: return f.read()

@app.get("/ai-search-gold", response_class=HTMLResponse)
async def ai_search_gold():
    with open("frontend/ai-search-gold.html") as f: return f.read()

@app.get("/ai-stop-optimize", response_class=HTMLResponse)
async def ai_stop_optimize():
    with open("frontend/ai-stop-optimize.html") as f: return f.read()

@app.get("/monetization", response_class=HTMLResponse)
async def monetization_page():
    with open("frontend/monetization.html") as f: return f.read()

@app.get("/ai-company-analysis", response_class=HTMLResponse)
async def ai_company_analysis():
    with open("frontend/ai-company-analysis.html") as f: return f.read()

# Redirect для обратной совместимости с расширением .html
@app.get("/ai-company-analysis.html", response_class=HTMLResponse)
async def ai_company_analysis_html():
    with open("frontend/ai-company-analysis.html") as f: return f.read()

@app.get("/ai-connect-models", response_class=HTMLResponse)
async def ai_connect_models():
    with open("frontend/ai-connect-models.html") as f: return f.read()

@app.get("/re-checking", response_class=HTMLResponse)
async def re_checking():
    with open("frontend/re-checking.html") as f: return f.read()

@app.get("/health")
async def health():
    return {"status": "ok"}

# Favicon — убирает 404 в консоли
FAVICON_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#8b5cf6"/><path fill="#fff" d="M16 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8zm0 10c3 0 6 1.5 6 3v2H10v-2c0-1.5 3-3 6-3z"/></svg>'

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")

# Chrome DevTools иногда запрашивает этот URL — отдаём пустой JSON, чтобы не было 404
@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
async def chrome_devtools():
    return Response(content=b"{}", media_type="application/json")

if __name__ == "__main__":
    import os
    import threading
    import time
    import webbrowser

    # Prevent opening multiple browser tabs during development reload
    if not os.environ.get("BROWSER_OPENED"):
        os.environ["BROWSER_OPENED"] = "true"
        
        def open_browser():
            time.sleep(1.5)  # Wait for uvicorn to bind and start listening
            url = f"http://127.0.0.1:{settings.port}"
            print(f"🌐 Automatically opening dashboard at {url}...")
            webbrowser.open(url)
            
        threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=True)
