from fastapi import APIRouter
from fastapi import HTTPException
from pydantic import BaseModel
from google.genai.errors import ClientError

from app.features.search_kis.service import run_kis_search
from app.services.kis_engine import kis_engine
from app.services.trake_engine import trake_engine
from app.services.translator import translator
from app.services.vqa_engine import vqa_engine

router = APIRouter()


class SearchRequest(BaseModel):
    type: str          # "KIS", "VQA", "TRAKE"
    text: str          # Mô tả tiếng Việt
    question: str | None = None
    top_k: int = 50


@router.post("/api/v1/search")
async def search(req: SearchRequest):
    if req.type == "KIS":
        try:
            return run_kis_search(req.text, req.top_k)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Keep old flow for VQA/TRAKE in this step
    en_text = translator.translate(req.text)

    try:
        if req.type == "VQA":
            top_kis = kis_engine.search(en_text, top_k=5)
            results = vqa_engine.answer(top_kis, req.question or "")
        elif req.type == "TRAKE":
            results = trake_engine.align(en_text, req.top_k)
        else:
            results = []
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "status": "success",
        "translated_text": en_text,
        "results": results
    }