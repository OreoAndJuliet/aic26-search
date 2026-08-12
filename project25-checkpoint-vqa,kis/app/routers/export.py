import csv
import zipfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()

SUBMISSION_DIR = Path("submission")
MAX_VQA_ANSWER_LENGTH = 100


class ExportItem(BaseModel):
    video_id: str = Field(min_length=1)
    frame_id: int = Field(ge=0)
    answer: str = ""


class SubmissionExportRequest(BaseModel):
    task_type: str
    results: list[ExportItem] = Field(min_length=1)


@router.post("/api/v1/export/submission")
async def export_submission(req: SubmissionExportRequest):
    validation_errors: list[str] = []

    if req.task_type not in {"KIS", "VQA", "TRAKE"}:
        validation_errors.append("task_type must be KIS, VQA, or TRAKE.")

    for index, item in enumerate(req.results):
        if req.task_type == "VQA" and len(item.answer) > MAX_VQA_ANSWER_LENGTH:
            validation_errors.append(
                f"results[{index}].answer exceeds {MAX_VQA_ANSWER_LENGTH} characters."
            )

    if validation_errors:
        return {
            "status": "FAILED",
            "csv_path": None,
            "zip_download_url": None,
            "validation_errors": validation_errors,
        }

    SUBMISSION_DIR.mkdir(exist_ok=True)

    export_id = uuid4().hex
    csv_filename = f"{req.task_type.lower()}_{export_id}.csv"
    zip_filename = f"{req.task_type.lower()}_{export_id}.zip"

    csv_path = SUBMISSION_DIR / csv_filename
    zip_path = SUBMISSION_DIR / zip_filename

    # newline="" and csv.writer provide correct CSV escaping for commas and quotes.
    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file, lineterminator="\n")

        for item in req.results:
            answer = item.answer[:MAX_VQA_ANSWER_LENGTH] if req.task_type == "VQA" else item.answer
            writer.writerow([item.video_id, item.frame_id, answer])

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(csv_path, arcname="submission.csv")

    return {
        "status": "SUCCESS",
        "csv_path": str(csv_path),
        "zip_download_url": f"/submission/{zip_filename}",
        "validation_errors": [],
    }