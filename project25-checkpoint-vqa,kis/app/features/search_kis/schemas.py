from pydantic import BaseModel, Field


class KisSearchRequest(BaseModel):
    query_text: str = Field(min_length=1)
    top_k: int = Field(default=50, ge=1, le=100)


class KisSearchResult(BaseModel):
    video_id: str
    frame_id: int
    score: float = Field(ge=0.0, le=1.0)
    image_url: str


class KisSearchResponse(BaseModel):
    results: list[KisSearchResult]
    latency_ms: float = Field(ge=0.0)