from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator

from app.core.config import settings


class SearchRequest(BaseModel):
    type: Literal["KIS", "VQA", "TRAKE"] = Field(
        default="KIS",
        validation_alias=AliasChoices("type", "query_type", "task_type"),
    )
    query: str | None = Field(
        default=None,
        validation_alias=AliasChoices("query", "text"),
        max_length=settings.MAX_QUERY_LENGTH,
    )
    events: list[str] = Field(default_factory=list)
    question: str | None = Field(default=None, max_length=settings.MAX_QUERY_LENGTH)
    top_k: int = Field(default=settings.TOP_K_DEFAULT, ge=1, le=settings.MAX_TOP_K)
    top_k_per_event: int = Field(default=100, ge=1, le=settings.MAX_TOP_K)
    max_gap_seconds: float = Field(default=300.0, ge=0.0, description="Maximum temporal gap between TRAKE events in seconds")
    video_filter: str | None = Field(
        default=None,
        validation_alias=AliasChoices("video_filter", "video_id", "video"),
        description="Filter results to specific video ID or video prefix (e.g. L23, L23_V001)",
    )

    @model_validator(mode="after")
    def validate_task_requirements(self) -> "SearchRequest":
        normalized_events = [event.strip() for event in self.events if event.strip()]
        object.__setattr__(self, "events", normalized_events)

        if normalized_events and (not self.query or not self.query.strip()):
            object.__setattr__(self, "type", "TRAKE")

        if self.type == "TRAKE":
            if not normalized_events and not (self.query and self.query.strip()):
                raise ValueError("TRAKE requires a non-empty events[] list or query/text.")
            return self

        if not self.query or not self.query.strip():
            raise ValueError("query/text is required for KIS and VQA.")
        return self

    def trake_events(self) -> list[str]:
        if self.events:
            return self.events
        if self.query is None:
            raise ValueError("Query cannot be None when events is empty")
        return [self.query.strip()]

    def display_query(self) -> str:
        if self.query and self.query.strip():
            return self.query.strip()
        return " | ".join(self.events)
