import time

from app.services.kis_engine import kis_engine
from app.services.translator import translator


def run_kis_search(text: str, top_k: int = 50) -> dict:
    started_at = time.perf_counter()

    en_text = translator.translate(text)
    results = kis_engine.search(en_text, top_k)

    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)

    return {
        "status": "success",
        "translated_text": en_text,
        "results": results,
        "latency_ms": latency_ms,
    }