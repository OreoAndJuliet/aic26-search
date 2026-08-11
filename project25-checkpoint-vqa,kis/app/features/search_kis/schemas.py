from pydantic import BaseModel


class KisSearchRequest(BaseModel):
    text: str
    top_k: int = 50


class KisSearchResponse(BaseModel):
    status: str
    translated_text: str
    results: list