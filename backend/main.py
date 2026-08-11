from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="AIC 2026 - Video Retrieval API")

# Cấu hình CORS để Frontend (thường chạy cổng 5173) có thể gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Trong môi trường dev có thể để *, production nên giới hạn
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Models ---
class SearchRequest(BaseModel):
    query_type: str  # "KIS", "VQA", "TRAKE"
    text: str
    question: Optional[str] = None
    top_k: int = 50

class SearchResult(BaseModel):
    video_id: str
    frame_id: int
    score: float
    thumbnail_url: str
    answer: Optional[str] = None

class SearchResponse(BaseModel):
    status: str
    data: List[SearchResult]

# --- Endpoints ---
@app.get("/")
def read_root():
    return {"message": "Welcome to AIC 2026 API Server. Access /docs for Swagger UI."}

@app.post("/api/v1/search", response_model=SearchResponse)
def search(request: SearchRequest):
    """
    API tìm kiếm chính (Mockup Data).
    Thực tế ở Giai đoạn 1, Backend sẽ cần gọi mô hình CLIP ở đây.
    """
    # Mock data để Frontend test giao diện trước
    mock_results = []
    for i in range(1, 21):
        mock_results.append(
            SearchResult(
                video_id=f"L01_V0{i:02d}",
                frame_id=1000 + i * 50,
                score=0.99 - (i * 0.01),
                thumbnail_url=f"https://picsum.photos/seed/{i}/300/200", # Ảnh giả để FE test
                answer="Đáp án mẫu" if request.query_type == "VQA" else None
            )
        )
    
    return SearchResponse(status="success", data=mock_results)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
