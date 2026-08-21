from pydantic import AliasChoices, BaseModel, Field

from app.core.config import settings


class KisSearchRequest(BaseModel):
    # query_text remains accepted for existing clients; query is the documented name.
    query: str = Field(
        validation_alias=AliasChoices("query", "query_text"),
        min_length=1,
        max_length=settings.MAX_QUERY_LENGTH,
    )
    top_k: int = Field(default=settings.TOP_K_DEFAULT, ge=1, le=settings.MAX_TOP_K)


class KisSearchResult(BaseModel):
    rank: int = Field(ge=1)
    video_id: str
    frame_id: int
    keyframe_id: int
    timestamp: float
    score: float = Field(ge=0.0, le=1.0)
    thumbnail_url: str
    image_url: str
    answer: str | None = None


class KisSearchResponse(BaseModel):
    status: str
    request_id: str
    query: str
    translated_query: str
    translated_text: str
    translation_applied: bool
    results: list[KisSearchResult]
    latency_ms: float = Field(ge=0.0)
    translation_time_ms: float = Field(ge=0.0)
    embedding_time_ms: float = Field(ge=0.0)
    faiss_time_ms: float = Field(ge=0.0)
    metadata_time_ms: float = Field(ge=0.0)
    retrieval_time_ms: float = Field(ge=0.0)
    total_time_ms: float = Field(ge=0.0)
