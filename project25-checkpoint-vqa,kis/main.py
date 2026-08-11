from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

from app.routers import export, search

app = FastAPI(title="AIC 2026 Backend System", version="1.0.0")

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

# 3. Đăng ký API Routers
app.include_router(search.router)
app.include_router(export.router)

@app.get("/")
def root():
    return {"status": "online", "system": "AIC 2026 Backend Engine"}
