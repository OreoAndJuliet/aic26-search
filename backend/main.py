import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.bootstrap import initialize_engines
from app.core.config import settings
from app.core.exceptions import BackendError
from app.core.logging import configure_logging
from app.routers import export, health, media, search

configure_logging(settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Load and validate the shared KIS resources before serving requests.

    When running in-test (AIC_TESTING=1) we skip heavy initialization so TestClient
    can control/mock engine state deterministically.
    """
    import os

    if os.getenv("AIC_TESTING"):
        # Tests will monkeypatch or pre-initialize kis_engine as needed
        yield
        return

    initialize_engines()
    yield

app = FastAPI(
    title="AIC 2026 Backend System",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(BackendError)
async def backend_error_handler(_: Request, exc: BackendError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


from fastapi.encoders import jsonable_encoder

@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": jsonable_encoder(exc.errors()),
            }
        },
    )

# 1. Cấu hình CORS mở cho React/Vite Frontend (hỗ trợ mọi port localhost/127.0.0.1)
cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Keyframe resolver must be registered before the static mount.
app.include_router(media.router)

# 3. Serve keyframes at the specification-required path: /keyframes/
# Ensure required directories exist before mounting
settings.KEYFRAMES_DIR.mkdir(parents=True, exist_ok=True)
settings.STATIC_DIR.mkdir(parents=True, exist_ok=True)
settings.SUBMISSION_DIR.mkdir(parents=True, exist_ok=True)

keyframes_path = str(settings.KEYFRAMES_DIR)
app.mount("/keyframes", StaticFiles(directory=keyframes_path), name="keyframes")

# 4. Serve static files at legacy path for backward compatibility
app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")
app.mount(
    "/submission",
    StaticFiles(directory=str(settings.SUBMISSION_DIR)),
    name="submission",
)
# 5. Đăng ký API Routers
# Register search router with /api prefix (creates /api/search and /api/search_trake and /api/v1/search)
app.include_router(search.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(health.router)  # Health check at root level for backward compatibility

@app.get("/")
def root():
    return {"status": "online", "system": "AIC 2026 Backend Engine"}
