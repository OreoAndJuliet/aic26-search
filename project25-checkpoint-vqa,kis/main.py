from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

from app.routers import export, search
from app.services.kis_engine import kis_engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Load the KIS text encoder before accepting requests."""
    kis_engine._ensure_model_loaded()
    yield


app = FastAPI(
    title="AIC 2026 Backend System",
    version="1.0.0",
    lifespan=lifespan,
)

# 1. Cấu hình CORS mở cho React/Vite Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Serves ảnh keyframes và video tĩnh
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/submission", StaticFiles(directory="submission"), name="submission")

# 3. Đăng ký API Routers
app.include_router(search.router)
app.include_router(export.router)

@app.get("/")
def root():
    return {"status": "online", "system": "AIC 2026 Backend Engine"}
