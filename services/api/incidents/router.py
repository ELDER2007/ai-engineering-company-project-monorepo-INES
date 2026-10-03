"""Routes for the incidents domain: analyze an uploaded CSV, export the last
analysis. Endpoint paths are fixed by the project brief, not the API
versioning convention used elsewhere in this monorepo's architecture
proposal — see docs/ARCHITECTURE_PROPOSAL.md for that broader discussion.

Errors of an uploaded file: ``413`` it is too big, ``422`` it cannot be processed (not a .csv,
not UTF-8, not CSV, missing columns, no rows). The export is each user's own last analysis.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response

from auth.dependencies import CurrentUser, get_current_user

from . import service
from .schemas import AnalyzeResponse

# Support-ticket data is internal: any valid session may analyze and export.
router = APIRouter(
    prefix="/api/incidents", tags=["incidents"], dependencies=[Depends(get_current_user)]
)

_UNPROCESSABLE = 422


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_incidents(file: UploadFile, user: CurrentUser) -> AnalyzeResponse:
    if file.size is not None and file.size > service.MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail="The file is too large.")
    try:
        content = await file.read(service.MAX_UPLOAD_BYTES + 1)
    except OSError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="The file could not be read.") from exc

    try:
        result = service.run_analysis(filename=file.filename or "upload.csv", content=content, owner=str(user.id))
    except service.FileTooLargeError as exc:
        raise HTTPException(413, detail=str(exc)) from exc
    except (
        service.NotCsvFileError,
        service.MissingColumnsError,
        service.EmptyCsvError,
        service.InvalidCsvError,
    ) as exc:
        raise HTTPException(_UNPROCESSABLE, detail=str(exc)) from exc
    except UnicodeDecodeError as exc:
        raise HTTPException(_UNPROCESSABLE, detail="File is not valid UTF-8 text.") from exc

    return service.to_response(result)


@router.get("/results/export")
async def export_results(user: CurrentUser) -> Response:
    try:
        result = service.get_last_result(str(user.id))
    except service.NoAnalysisYetError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    csv_bytes = service.to_export_csv_bytes(result)
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="results.csv"'},
    )
