from pathlib import Path

from fastapi import APIRouter
from fastapi import HTTPException
from pydantic import BaseModel
from google.genai.errors import ClientError

from app.features.search_kis.schemas import KisSearchRequest, KisSearchResponse
from app.features.search_kis.service import run_kis_search
from app.services.kis_engine import kis_engine
from app.services.object_store import object_store
from app.services.trake_engine import trake_engine
from app.services.translator import translator
from app.services.vqa_engine import vqa_engine

router = APIRouter()

COUNT_WORDS = ("how many", "number of", "bao nhiêu", "bao nhieu", "số lượng")
PERSON_WORDS = ("person", "people", "human", "người", "nguoi")


def _is_person_count_question(question: str) -> bool:
    normalized = question.casefold()
    return (
        any(word in normalized for word in COUNT_WORDS)
        and any(word in normalized for word in PERSON_WORDS)
    )


def _answer_person_count(top_kis_results: list[dict], question: str) -> list[dict]:
    """Use Objects JSON first, then ask Gemini only for uncertain counts."""
    if not top_kis_results:
        return []

    candidate = top_kis_results[0].copy()
    keyframe_id = int(candidate.get("keyframe_id", candidate["frame_id"]))
    json_result = object_store.count_with_confidence(
        candidate["video_id"],
        keyframe_id,
        "person",
    )

    candidate["json_count"] = json_result["count"]
    candidate["json_bboxes"] = json_result["bboxes"]
    candidate["fallback_reasons"] = json_result["fallback_reasons"]

    if json_result["should_use_vlm"]:
        image_path = (
            Path("static")
            / "keyframes"
            / candidate["video_id"]
            / f"{keyframe_id:03d}.jpg"
        )
        vlm_raw_log = vqa_engine.answer_single_image(
            image_path,
            "Count the visible people. Return only the number.",
        )
        candidate["answer"] = vlm_raw_log[:100]
        candidate["source"] = "VLM_API"
        candidate["vlm_raw_log"] = vlm_raw_log
    else:
        candidate["answer"] = str(json_result["count"])
        candidate["source"] = "FASTER_RCNN_JSON"
        candidate["vlm_raw_log"] = ""

    return [candidate]


class SearchRequest(BaseModel):
    type: str          # "KIS", "VQA", "TRAKE"
    text: str          # Mô tả tiếng Việt
    question: str | None = None
    top_k: int = 50

@router.post("/api/v1/search/kis", response_model=KisSearchResponse)
async def search_kis(req: KisSearchRequest):
    try:
        response = run_kis_search(req.query_text, req.top_k)

        return {
            "results": response["results"],
            "latency_ms": response["latency_ms"],
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    
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
            if _is_person_count_question(req.question or ""):
                results = _answer_person_count(top_kis, req.question or "")
            else:
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
    
