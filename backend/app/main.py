from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
from typing import Any
from uuid import UUID
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import current_user, require_roles, router as auth_router
from .database import get_db
from .models import Asset, Company, Inspection, PipeSection, Project, User
from .reports import render_report_html, render_report_pdf
from .schemas import INPUT_SCHEMAS
from .storage import LocalAssetStorage, storage_key_exists
from .survey_api import router as survey_router

app = FastAPI(title="CCTV Survey Report Automation API", version="0.1.0", description="CCTV survey records, Dashboard and project-specific report generation API")
app.include_router(auth_router)
app.include_router(survey_router)

MODEL_MAP = {"companies": Company, "users": User, "projects": Project, "pipe-sections": PipeSection, "assets": Asset, "inspections": Inspection}
READ_ROLES = ("ADMIN", "PROJECT_MANAGER", "OPERATOR", "VIEWER")
WRITE_ROLES = {
    "companies": ("ADMIN",), "users": ("ADMIN",),
    "projects": ("ADMIN", "PROJECT_MANAGER"),
    "pipe-sections": ("ADMIN", "PROJECT_MANAGER", "OPERATOR"),
    "assets": ("ADMIN", "PROJECT_MANAGER", "OPERATOR"),
    "inspections": ("ADMIN", "PROJECT_MANAGER", "OPERATOR"),
}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mpeg", ".mpg", ".webm", ".ts", ".vob"}
MAX_VIDEO_UPLOAD_BYTES = int(os.getenv("CCTV_MAX_VIDEO_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024)))


def serialize(instance: Any) -> dict[str, Any]:
    return jsonable_encoder({
        column.name: getattr(instance, column.name)
        for column in instance.__table__.columns
        if column.name != "password_hash"
    })


def validate_inspection_video(db: Session, payload: dict[str, Any]) -> None:
    asset_id = payload.get("video_asset_id")
    if not asset_id:
        return
    pipe = db.get(PipeSection, payload["pipe_section_id"])
    asset = db.get(Asset, asset_id)
    if not pipe or not asset or asset.file_type != "VIDEO" or asset.project_id != pipe.project_id or not asset.sha256_hash or not storage_key_exists(asset.storage_key):
        raise HTTPException(422, "The video must be an uploaded VIDEO asset from the same project.")


def make_router(path: str, model: Any) -> None:
    schema = INPUT_SCHEMAS[path]
    base_path = f"/api/{path}"

    def list_items(db: Session = Depends(get_db), _user: User = Depends(require_roles(*READ_ROLES)), limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        rows = db.scalars(select(model).order_by(model.created_at.desc()).limit(limit).offset(offset)).all()
        return {"items": [serialize(row) for row in rows], "limit": limit, "offset": offset}

    def get_item(item_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles(*READ_ROLES))):
        item = db.get(model, item_id)
        if not item:
            raise HTTPException(404, "The requested record was not found.")
        return serialize(item)

    def create_item(payload: dict[str, Any], db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES[path]))):
        try:
            values = schema.model_validate(payload).model_dump()
        except ValidationError as exc:
            raise HTTPException(422, detail=exc.errors(include_url=False)) from exc
        if model is Project:
            values["created_by"] = user.id
        if model is Asset:
            if values.get("file_type") == "VIDEO":
                raise HTTPException(422, "CCTV videos must be created by uploading the actual file; metadata-only video records are not permitted.")
            values["uploaded_by"] = user.id
        if model is Inspection:
            if not values.get("inspection_number"):
                current_max = db.scalar(select(func.max(Inspection.inspection_number)).where(Inspection.pipe_section_id == values["pipe_section_id"])) or 0
                values["inspection_number"] = int(current_max) + 1
            validate_inspection_video(db, values)
        item = model(**values)
        db.add(item)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "The record violates a unique, foreign-key or database constraint.") from exc
        db.refresh(item)
        return serialize(item)

    def update_item(item_id: UUID, payload: dict[str, Any], db: Session = Depends(get_db), _user: User = Depends(require_roles(*WRITE_ROLES[path]))):
        item = db.get(model, item_id)
        if not item:
            raise HTTPException(404, "The requested record was not found.")
        try:
            current_values = {name: getattr(item, name) for name in schema.model_fields}
            validated = schema.model_validate(current_values | payload).model_dump()
        except ValidationError as exc:
            raise HTTPException(422, detail=exc.errors(include_url=False)) from exc
        if model is Inspection:
            validate_inspection_video(db, validated)
        if model is Asset and (item.file_type == "VIDEO" or validated.get("file_type") == "VIDEO"):
            raise HTTPException(422, "Uploaded CCTV video records cannot be manually edited through asset CRUD.")
        for key in payload:
            setattr(item, key, validated[key])
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "The update violates a unique, foreign-key or database constraint.") from exc
        db.refresh(item)
        return serialize(item)

    def delete_item(item_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles(*WRITE_ROLES[path]))):
        item = db.get(model, item_id)
        if not item:
            raise HTTPException(404, "The requested record was not found.")
        db.delete(item)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "This record is still referenced by related records and cannot be deleted.") from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    endpoints = (
        (list_items, "GET", "", [200]), (get_item, "GET", "/{item_id}", [200, 404]),
        (create_item, "POST", "", [201, 409, 422]), (update_item, "PATCH", "/{item_id}", [200, 404, 409, 422]),
        (delete_item, "DELETE", "/{item_id}", [204, 404, 409]),
    )
    for endpoint, method, suffix, codes in endpoints:
        endpoint.__name__ = f"{path.replace('-', '_')}_{method.lower()}_{'item' if suffix else 'list_or_create'}"
        app.add_api_route(base_path + suffix, endpoint, methods=[method], status_code=201 if method == "POST" else 200, responses={code: {"description": "API response"} for code in codes if code not in (200, 201)})


for resource, resource_model in MODEL_MAP.items():
    make_router(resource, resource_model)


@app.post("/api/projects/{project_id}/videos", status_code=201)
def upload_project_video(project_id: UUID, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "PROJECT_MANAGER", "OPERATOR"))):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "The requested project was not found.")
    original_name = (file.filename or "").replace("\\", "/")
    file_name = Path(original_name).name
    extension = Path(file_name).suffix.lower()
    if not file_name or file_name in {".", ".."} or "\x00" in file_name:
        raise HTTPException(422, "Provide a valid video file name.")
    mime_type = (file.content_type or "").lower()
    if extension not in VIDEO_EXTENSIONS or (mime_type and not mime_type.startswith("video/") and mime_type != "application/octet-stream"):
        raise HTTPException(415, "Only supported CCTV video files (MP4, MOV, MKV, AVI, MPEG, WebM and similar formats) are accepted.")
    size = file.size
    if size is None:
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
    if size <= 0:
        raise HTTPException(422, "The CCTV video file is empty.")
    if size > MAX_VIDEO_UPLOAD_BYTES:
        raise HTTPException(413, f"The video file exceeds the configured upload limit of {MAX_VIDEO_UPLOAD_BYTES} bytes.")
    try:
        stored = LocalAssetStorage().save(file_name, file.file, str(project.id))
    except (OSError, ValueError) as exc:
        raise HTTPException(500, "The video file could not be stored.") from exc
    asset = Asset(company_id=project.company_id, project_id=project.id, file_name=stored.file_name, storage_key=stored.storage_key, file_type="VIDEO", mime_type=mime_type or "application/octet-stream", file_size_bytes=stored.file_size_bytes, sha256_hash=stored.sha256_hash, uploaded_by=user.id)
    db.add(asset)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "The CCTV video metadata could not be saved.") from exc
    db.refresh(asset)
    return serialize(asset)


@app.get("/api/projects/{project_id}/videos")
def list_project_videos(project_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles(*READ_ROLES))):
    if not db.get(Project, project_id):
        raise HTTPException(404, "The requested project was not found.")
    rows = db.scalars(select(Asset).where(Asset.project_id == project_id, Asset.file_type == "VIDEO").order_by(Asset.created_at.desc())).all()
    rows = [row for row in rows if row.sha256_hash and storage_key_exists(row.storage_key)]
    return {"items": [serialize(row) for row in rows]}


@app.get("/api/assets/{asset_id}/download")
def download_asset(asset_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles(*READ_ROLES))):
    asset = db.get(Asset, asset_id)
    if not asset or not asset.storage_key:
        raise HTTPException(404, "The uploaded file record was not found.")
    try:
        stream = LocalAssetStorage().open(asset.storage_key)
    except (OSError, ValueError) as exc:
        raise HTTPException(404, "The file is not present in the current storage location.") from exc
    disposition_name = quote(asset.file_name, safe="")
    return StreamingResponse(stream, media_type=asset.mime_type or "application/octet-stream", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{disposition_name}"})


@app.get("/api/projects/{project_id}/report-data")
def project_report_data(project_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles(*READ_ROLES))):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "The requested project was not found.")
    pipe_ids = db.scalars(select(PipeSection.id).where(PipeSection.project_id == project_id)).all()
    inspection_count = db.scalar(select(func.count(Inspection.id)).where(Inspection.pipe_section_id.in_(pipe_ids))) if pipe_ids else 0
    linked_inspections = db.scalars(select(Inspection).join(PipeSection).where(PipeSection.project_id == project_id, Inspection.video_asset_id.is_not(None))).all()
    video_count = sum(1 for inspection in linked_inspections if (asset := db.get(Asset, inspection.video_asset_id)) and asset.file_type == "VIDEO" and asset.sha256_hash and storage_key_exists(asset.storage_key))
    return {"project": serialize(project), "company_name": project.company.company_name, "pipe_section_count": len(pipe_ids), "inspection_count": inspection_count or 0, "video_count": video_count}


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db), _user: User = Depends(require_roles(*READ_ROLES))):
    projects = db.scalars(select(Project).order_by(Project.updated_at.desc())).all()
    project_rows = []
    for project in projects:
        section_count = db.scalar(select(func.count(PipeSection.id)).where(PipeSection.project_id == project.id)) or 0
        inspection_count = db.scalar(select(func.count(Inspection.id)).join(PipeSection).where(PipeSection.project_id == project.id)) or 0
        project_rows.append({"id": str(project.id), "project_code": project.project_code, "project_name": project.project_name, "client_name": project.client_name, "location": project.location, "status": project.status, "report_status": project.report_status, "pipe_section_count": section_count, "inspection_count": inspection_count, "report_date": project.report_date})
    pipes_by_status = {key: value for key, value in db.execute(select(PipeSection.survey_status, func.count()).group_by(PipeSection.survey_status)).all()}
    inspections_by_status = {key: value for key, value in db.execute(select(Inspection.inspection_status, func.count()).group_by(Inspection.inspection_status)).all()}
    return {"totals": {"projects": len(project_rows), "pipe_sections": sum(pipes_by_status.values()), "inspections": sum(inspections_by_status.values())}, "pipe_sections_by_status": pipes_by_status, "inspections_by_status": inspections_by_status, "projects": project_rows}


@app.get("/api/projects/{project_id}/report.html", response_class=HTMLResponse)
def project_report_html(project_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles(*READ_ROLES))):
    try:
        html = render_report_html(db, str(project_id))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return HTMLResponse(html, headers={"Content-Disposition": "inline; filename=cctv-survey-report.html"})


@app.get("/api/projects/{project_id}/report.pdf")
def project_report_pdf(project_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "PROJECT_MANAGER"))):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "The requested project was not found.")
    try:
        data = render_report_pdf(db, str(project_id))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    project.report_status = "GENERATED"
    db.commit()
    safe_code = "".join(char for char in project.project_code if char.isalnum() or char in "-_.")[:100] or str(project.id)
    return StreamingResponse(BytesIO(data), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="cctv-survey-{safe_code}.pdf"'})


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "cctv-survey-api", "version": "0.1.0"}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


DIST_DIR = Path(__file__).resolve().parents[2] / "dist"


@app.get("/{frontend_path:path}", include_in_schema=False)
def serve_frontend(frontend_path: str):
    if frontend_path == "api" or frontend_path.startswith("api/"):
        raise HTTPException(404, "The requested API endpoint was not found.")
    index = DIST_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(404, "The frontend build is not available.")
    requested = (DIST_DIR / frontend_path).resolve()
    if DIST_DIR.resolve() not in requested.parents and requested != DIST_DIR.resolve():
        raise HTTPException(404, "The requested file was not found.")
    if requested.is_file():
        return FileResponse(requested)
    if Path(frontend_path).suffix:
        raise HTTPException(404, "The requested file was not found.")
    return FileResponse(index)
