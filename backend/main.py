from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn
from backend.config import settings
from backend.database import check_db_connection
from backend.routers import upload_router, metrics_router, bot_agent_router, ai_settings_router

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

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    with open("frontend/index.html") as f: return f.read()

@app.get("/top5", response_class=HTMLResponse)
async def top5():
    with open("frontend/top5.html") as f: return f.read()

@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
    with open("frontend/settings.html") as f: return f.read()

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=True)
