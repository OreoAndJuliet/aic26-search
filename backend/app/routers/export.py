import json
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import settings
from app.features.submission.adapter import (
    MAX_VQA_ANSWER_LENGTH,
    build_answer_set,
    build_submission_payload,
    results_to_csv_rows,
)
from app.features.submission.csv_export import (
    build_codabench_zip,
    codabench_csv_name,
    write_submission_csv,
)

router = APIRouter()



SUBMISSION_DIR = settings.SUBMISSION_DIR





class ExportItem(BaseModel):

    video_id: str = Field(min_length=1)

    frame_id: int = Field(ge=0)

    answer: str = ""





class SubmissionExportRequest(BaseModel):

    task_type: str

    results: list[ExportItem] = Field(min_length=1)

    trake_meta: dict | None = None

    team_session_id: str | None = None

    query_id: int = Field(default=1, ge=1)





class SubmissionFromSearchRequest(BaseModel):

    task_type: str

    search_response: dict

    team_session_id: str | None = None

    query_id: int = Field(default=1, ge=1)





@router.post("/v1/export/submission")
@router.post("/export/submission")
@router.post("/export/csv")
async def export_submission(req: SubmissionExportRequest):

    validation_errors: list[str] = []



    try:

        if req.task_type not in {"KIS", "VQA", "TRAKE", "QA", "TR"}:

            validation_errors.append("task_type must be KIS, VQA, TRAKE, QA, or TR.")

        else:

            rows = results_to_csv_rows(

                req.task_type,

                [item.model_dump() for item in req.results],

                trake_meta=req.trake_meta,

            )

            for index, row in enumerate(rows):

                if req.task_type in {"VQA", "QA"} and len(row) >= 3:

                    answer = str(row[2])

                    if len(answer) > MAX_VQA_ANSWER_LENGTH:

                        validation_errors.append(

                            f"results[{index}].answer exceeds {MAX_VQA_ANSWER_LENGTH} characters."

                        )

    except ValueError as exc:

        validation_errors.append(str(exc))



    if validation_errors:

        return {

            "status": "FAILED",

            "csv_path": None,

            "zip_download_url": None,

            "submission_json": None,

            "validation_errors": validation_errors,

        }



    SUBMISSION_DIR.mkdir(exist_ok=True)



    export_id = uuid4().hex

    csv_filename = codabench_csv_name(req.query_id, req.task_type)

    zip_filename = f"{req.task_type.lower()}_{export_id}.zip"

    json_filename = f"{req.task_type.lower()}_{export_id}.json"



    submission_dir = SUBMISSION_DIR / "submission"

    csv_path = submission_dir / csv_filename

    zip_path = SUBMISSION_DIR / zip_filename

    json_path = SUBMISSION_DIR / json_filename



    rows = results_to_csv_rows(

        req.task_type,

        [item.model_dump() for item in req.results],

        trake_meta=req.trake_meta,

    )

    write_submission_csv(csv_path, rows, task_type=req.task_type)

    build_codabench_zip(

        zip_path,

        [(csv_filename, rows, req.task_type)],

    )



    answer_set = build_answer_set(

        req.task_type,

        [item.model_dump() for item in req.results],

        trake_meta=req.trake_meta,

    )

    submission_json = build_submission_payload(

        req.team_session_id or "local-dev-session",

        [answer_set],

    )

    json_path.write_text(json.dumps(submission_json, indent=2), encoding="utf-8")



    return {

        "status": "SUCCESS",

        "csv_path": str(csv_path),

        "zip_download_url": f"/submission/{zip_filename}",

        "submission_json_path": str(json_path),

        "submission_json": submission_json,

        "validation_errors": [],

    }





@router.post("/v1/export/submission/from-search")
@router.post("/export/submission/from-search")
async def export_submission_from_search(req: SubmissionFromSearchRequest):

    try:

        answer_set = build_answer_set(

            req.task_type,

            req.search_response.get("results", []),

            trake_meta=req.search_response.get("trake"),

        )

        rows = results_to_csv_rows(

            req.task_type,

            req.search_response.get("results", []),

            trake_meta=req.search_response.get("trake"),

        )

    except ValueError as exc:

        return {

            "status": "FAILED",

            "validation_errors": [str(exc)],

        }



    SUBMISSION_DIR.mkdir(exist_ok=True)

    export_id = uuid4().hex

    csv_filename = codabench_csv_name(req.query_id, req.task_type)

    csv_path = SUBMISSION_DIR / "submission" / csv_filename

    zip_path = SUBMISSION_DIR / f"search_{export_id}.zip"

    json_path = SUBMISSION_DIR / f"search_{export_id}.json"



    write_submission_csv(csv_path, rows, task_type=req.task_type)

    build_codabench_zip(zip_path, [(csv_filename, rows, req.task_type)])



    submission_json = build_submission_payload(

        req.team_session_id or "local-dev-session",

        [answer_set],

    )

    json_path.write_text(json.dumps(submission_json, indent=2), encoding="utf-8")



    return {

        "status": "SUCCESS",

        "csv_path": str(csv_path),

        "zip_download_url": f"/submission/{zip_path.name}",

        "submission_json_path": str(json_path),

        "submission_json": submission_json,

        "validation_errors": [],

    }


