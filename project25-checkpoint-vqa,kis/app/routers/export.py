
from fastapi import APIRouter, Response
from pydantic import BaseModel

router = APIRouter()

class ExportItem(BaseModel):
    video_id: str
    frame_id: int
    answer: str | None = ""

@router.post("/api/v1/export/csv")
async def export_csv(items: list[ExportItem]):
    """Xuất file CSV theo chuẩn AIC: Không header, định dạng: <video_id>,<frame_id>,"<answer>\""""
    lines = []
    for item in items:
        ans = item.answer if item.answer else ""
        lines.append(f'{item.video_id},{item.frame_id},"{ans}"')
    
    csv_content = "\n".join(lines)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=submission.csv"}
    )
