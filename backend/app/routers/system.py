import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
import asyncio

from build_index import build_real_faiss_index
from app.services.kis_engine import kis_engine

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/rebuild-index")
async def rebuild_index(background_tasks: BackgroundTasks):
    """
    Rebuild the FAISS index from .npy features and hot-reload it in KISEngine.
    Runs asynchronously in the background.
    Endpoint: POST /api/system/rebuild-index
    """
    def _rebuild_and_reload():
        try:
            logger.info("Starting FAISS index rebuild...")
            build_real_faiss_index()
            logger.info("Rebuild complete. Triggering KIS Engine hot-reload...")
            kis_engine.reload_index()
            logger.info("Hot-reload complete.")
        except Exception as exc:
            logger.exception("Failed to rebuild and reload index: %s", exc)

    background_tasks.add_task(_rebuild_and_reload)
    return {"status": "success", "message": "Index rebuild and hot-reload started in background."}
