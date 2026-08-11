from app.services.kis_engine import kis_engine
from app.services.translator import translator


def run_kis_search(text: str, top_k: int = 50) -> dict:
    en_text = translator.translate(text)
    results = kis_engine.search(en_text, top_k)

    return {
        "status": "success",
        "translated_text": en_text,
        "results": results,
    }