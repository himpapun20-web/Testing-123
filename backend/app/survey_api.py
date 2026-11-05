from __future__ import annotations

from datetime import date
from io import BytesIO
from decimal import Decimal
from pathlib import Path
import json
import os
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import require_roles
from .database import get_db
from .filename_parser import parse_survey_filename
from .frame_capture import extract_frame
from .models import Asset, Company, Inspection, InspectionEvent, PipeSection, Project, User
from .schemas import FilenamePreviewInput, InspectionEventInput, SurveyFileMetadata
from .storage import FileTooLargeError, LocalAssetStorage, storage_key_exists

router = APIRouter(prefix="/api", tags=["survey import and evidence"])
READ_ROLES = ("ADMIN", "PROJECT_MANAGER", "OPERATOR", "VIEWER")
EDIT_ROLES = ("ADMIN", "PROJECT_MANAGER", "OPERATOR")
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mpeg", ".mpg", ".webm", ".ts", ".vob"}
MAX_VIDEO_UPLOAD_BYTES = int(os.getenv("CCTV_MAX_VIDEO_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024)))
MAX_SITE_PLAN_BYTES = int(os.getenv("CCTV_MAX_SITE_PLAN_UPLOAD_BYTES", str(25 * 1024 * 1024)))
SITE_PLAN_MIMES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
MATERIAL_NAMES = {"DI": "Ductile iron", "CO": "Concrete", "PVC": "PVC"}


def serialize(instance: Any) -> dict[str, Any]:
    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder({column.name: getattr(instance, column.name) for column in instance.__table__.columns})


def _safe_file_name(file: UploadFile) -> str:
    original = (file.filename or "").replace("\\", "/")
    safe_name = Path(original).name
    if not safe_name or safe_name in {".", ".."} or "\x00" in safe_name:
        raise HTTPException(422, "Each video must have a valid file name.")
    return safe_name


def _validate_video(file: UploadFile) -> tuple[str, str]:
    safe_name = _safe_file_name(file)
    extension = Path(safe_name).suffix.lower()
    mime_type = (file.content_type or "").lower()
    if extension not in VIDEO_EXTENSIONS or (mime_type and not mime_type.startswith("video/") and mime_type != "application/octet-stream"):
        raise HTTPException(415, "Only supported CCTV video files are accepted.")
    return safe_name, mime_type or "application/octet-stream"


def _canonical_nodes(row: SurveyFileMetadata) -> tuple[str, str]:
    # A camera moving upstream starts at the downstream node; a camera moving downstream starts upstream.
    if row.inspection_direction == "UPSTREAM":
        return row.finish_manhole, row.start_manhole
    return row.start_manhole, row.finish_manhole


def _get_or_create_pipe(db: Session, project: Project, row: SurveyFileMetadata) -> PipeSection:
    upstream_node, downstream_node = _canonical_nodes(row)
    pipe = db.scalar(select(PipeSection).where(
        PipeSection.project_id == project.id,
        PipeSection.start_manhole == upstream_node,
        PipeSection.finish_manhole == downstream_node,
    ).order_by(PipeSection.created_at).limit(1))
    if pipe:
        return pipe
    section_reference = f"{upstream_node} > {downstream_node}"
    pipe = PipeSection(
        project_id=project.id,
        pipe_id=f"{upstream_node}X",
        section_reference=section_reference,
        start_manhole=upstream_node,
        finish_manhole=downstream_node,
        survey_length_m=row.survey_length_m,
        pipe_size_mm=row.pipe_size_mm,
        pipe_material_code=row.pipe_material_code,
        pipe_material_description=MATERIAL_NAMES.get((row.pipe_material_code or "").upper(), row.pipe_material_code),
        survey_status="IN_PROGRESS",
        remarks=f"Location parsed from video filename: {row.filename_location}" if row.filename_location else None,
    )
    db.add(pipe)
    db.flush()
    return pipe


@router.post("/projects/{project_id}/filename-preview")
def preview_filenames(project_id: UUID, payload: FilenamePreviewInput, db: Session = Depends(get_db), _user: User = Depends(require_roles(*READ_ROLES))):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found.")
    return {"items": [parse_survey_filename(name) for name in payload.filenames]}


@router.post("/projects/{project_id}/survey-batch", status_code=201)
def upload_survey_batch(
    project_id: UUID,
    files: list[UploadFile] = File(...),
    metadata_json: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*EDIT_ROLES)),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found.")
    if not files or len(files) > 50:
        raise HTTPException(422, "Select between 1 and 50 video files per batch.")
    try:
        raw_rows = json.loads(metadata_json)
        if not isinstance(raw_rows, list) or len(raw_rows) != len(files):
            raise ValueError("The reviewed filename data must have one row per selected video.")
        rows = [SurveyFileMetadata.model_validate(row) for row in raw_rows]
    except (json.JSONDecodeError, ValueError, ValidationError) as exc:
        raise HTTPException(422, "Reviewed filename data is invalid. Correct the highlighted fields and try again.") from exc

    names: list[str] = []
    for file, row in zip(files, rows, strict=True):
        safe_name, _ = _validate_video(file)
        if safe_name != row.file_name:
            raise HTTPException(422, "The selected file names changed after filename review. Select the files again.")
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        if size <= 0:
            raise HTTPException(422, f"{safe_name} is empty.")
        if size > MAX_VIDEO_UPLOAD_BYTES:
            raise HTTPException(413, f"{safe_name} exceeds the per-video upload limit of {MAX_VIDEO_UPLOAD_BYTES} bytes.")
        names.append(safe_name)

    reviewed_locations = [(row.filename_location or "").strip() for row in rows]
    normalized_locations = {location.casefold() for location in reviewed_locations}
    if not (project.location or "").strip() and all(reviewed_locations) and len(normalized_locations) == 1:
        project.location = reviewed_locations[0]

    storage = LocalAssetStorage()
    created_storage_keys: list[str] = []
    response_rows = []
    start_dates: list[date] = []
    end_dates: list[date] = []
    try:
        for file, row in zip(files, rows, strict=True):
            safe_name, mime_type = _validate_video(file)
            stored = storage.save(safe_name, file.file, str(project.id), max_bytes=MAX_VIDEO_UPLOAD_BYTES)
            created_storage_keys.append(stored.storage_key)
            if stored.file_size_bytes == 0:
                raise HTTPException(422, f"{safe_name} is empty.")
            asset = Asset(
                company_id=project.company_id,
                project_id=project.id,
                file_name=stored.file_name,
                storage_key=stored.storage_key,
                file_type="VIDEO",
                mime_type=mime_type,
                file_size_bytes=stored.file_size_bytes,
                sha256_hash=stored.sha256_hash,
                uploaded_by=user.id,
                metadata_json={"filename_import": {"original_filename": safe_name, "source_date_label": row.source_date_label, "inspection_date": row.inspection_date.isoformat(), "survey_end_date": (row.survey_end_date or row.inspection_date).isoformat(), "start_manhole": row.start_manhole, "finish_manhole": row.finish_manhole, "inspection_direction": row.inspection_direction, "filename_location": row.filename_location}},
            )
            db.add(asset)
            db.flush()
            pipe = _get_or_create_pipe(db, project, row)
            existing_number = db.scalar(select(func.max(Inspection.inspection_number)).where(Inspection.pipe_section_id == pipe.id)) or 0
            inspection = Inspection(
                pipe_section_id=pipe.id,
                video_asset_id=asset.id,
                inspection_number=int(existing_number) + 1,
                inspection_date=row.inspection_date,
                inspection_direction=row.inspection_direction,
                preset_length_m=row.survey_length_m,
                inspection_status="IN_PROGRESS",
            )
            db.add(inspection)
            db.flush()
            response_rows.append({"file_name": safe_name, "asset_id": str(asset.id), "inspection_id": str(inspection.id), "pipe_section_id": str(pipe.id), "pipe_id": pipe.pipe_id, "upstream_manhole": pipe.start_manhole, "downstream_manhole": pipe.finish_manhole, "inspection_direction": row.inspection_direction, "inspection_date": row.inspection_date.isoformat(), "survey_length_m": str(row.survey_length_m)})
            start_dates.append(row.inspection_date)
            end_dates.append(row.survey_end_date or row.inspection_date)
        project.survey_start_date = min([d for d in [project.survey_start_date, *start_dates] if d is not None])
        project.survey_end_date = max([d for d in [project.survey_end_date, *end_dates] if d is not None])
        project.status = "IN_PROGRESS" if project.status == "DRAFT" else project.status
        project.report_status = "DRAFT"
        db.commit()
    except HTTPException:
        db.rollback()
        for key in created_storage_keys:
            storage.delete(key)
        raise
    except FileTooLargeError as exc:
        db.rollback()
        for key in created_storage_keys:
            storage.delete(key)
        raise HTTPException(413, "A video exceeds the configured per-file upload limit.") from exc
    except (IntegrityError, OSError, ValueError) as exc:
        db.rollback()
        for key in created_storage_keys:
            storage.delete(key)
        raise HTTPException(422, "The video batch could not be saved. Check the selected files and project data.") from exc
    return {"created": response_rows, "count": len(response_rows)}


def _event_response(event: InspectionEvent, inspection: Inspection, pipe: PipeSection, video: Asset, photo: Asset | None) -> dict[str, Any]:
    return {
        **serialize(event),
        "inspection_date": inspection.inspection_date,
        "inspection_direction": inspection.inspection_direction,
        "inspection_number": inspection.inspection_number,
        "pipe_id": pipe.pipe_id,
        "upstream_manhole": pipe.start_manhole,
        "downstream_manhole": pipe.finish_manhole,
        "video_file_name": video.file_name,
        "photo_file_name": photo.file_name if photo else None,
        "photo_download_url": f"/api/assets/{photo.id}/download" if photo else None,
    }


def _extract_photo(db: Session, project: Project, inspection: Inspection, video: Asset, event: InspectionEvent, user: User, storage: LocalAssetStorage) -> Asset:
    if not video.storage_key or not video.sha256_hash or not storage.path_for(video.storage_key).is_file():
        raise HTTPException(422, "The selected CCTV video is not present in project storage.")
    try:
        frame = extract_frame(storage.path_for(video.storage_key), float(event.timestamp_seconds))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (OSError, RuntimeError) as exc:
        raise HTTPException(503, "The frame extraction service could not read this video.") from exc
    stored = storage.save_bytes(f"inspection-{inspection.id}-event-{event.event_number:03d}.png", frame.content, str(project.id))
    return Asset(company_id=project.company_id, project_id=project.id, file_name=stored.file_name, storage_key=stored.storage_key, file_type="PHOTO", mime_type=frame.mime_type, file_size_bytes=stored.file_size_bytes, sha256_hash=stored.sha256_hash, width_px=frame.width_px, height_px=frame.height_px, uploaded_by=user.id, metadata_json={"inspection_event_id": str(event.id), "video_asset_id": str(video.id), "timestamp_seconds": str(event.timestamp_seconds), "extracted_from_video": True})


def _inspection_context(db: Session, inspection_id: UUID) -> tuple[Inspection, PipeSection, Project, Asset]:
    inspection = db.get(Inspection, inspection_id)
    if not inspection:
        raise HTTPException(404, "Inspection not found.")
    pipe = db.get(PipeSection, inspection.pipe_section_id)
    project = db.get(Project, pipe.project_id) if pipe else None
    video = db.get(Asset, inspection.video_asset_id) if inspection.video_asset_id else None
    if not pipe or not project:
        raise HTTPException(404, "The inspection's pipe section was not found.")
    if not video or video.file_type != "VIDEO":
        raise HTTPException(422, "This inspection has no linked CCTV video.")
    return inspection, pipe, project, video


@router.get("/projects/{project_id}/events")
def list_project_events(project_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles(*READ_ROLES))):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found.")
    events = db.scalars(select(InspectionEvent).join(Inspection).join(PipeSection).where(PipeSection.project_id == project_id).order_by(PipeSection.pipe_id, InspectionEvent.distance_m, InspectionEvent.event_number)).all()
    result = []
    for event in events:
        inspection = db.get(Inspection, event.inspection_id)
        pipe = db.get(PipeSection, inspection.pipe_section_id) if inspection else None
        video = db.get(Asset, event.video_asset_id)
        photo = db.get(Asset, event.photo_asset_id) if event.photo_asset_id else None
        if inspection and pipe and video:
            result.append(_event_response(event, inspection, pipe, video, photo))
    return {"items": result}


@router.post("/inspections/{inspection_id}/events", status_code=201)
def create_inspection_event(inspection_id: UUID, payload: InspectionEventInput, db: Session = Depends(get_db), user: User = Depends(require_roles(*EDIT_ROLES))):
    inspection, pipe, project, video = _inspection_context(db, inspection_id)
    section_length = pipe.survey_length_m or inspection.preset_length_m
    if section_length is not None and payload.distance_m > section_length:
        raise HTTPException(422, "Event distance cannot exceed the recorded pipe section length.")
    storage = LocalAssetStorage()
    event_number = int(db.scalar(select(func.max(InspectionEvent.event_number)).where(InspectionEvent.inspection_id == inspection.id)) or 0) + 1
    event = InspectionEvent(inspection_id=inspection.id, video_asset_id=video.id, event_number=event_number, event_type=payload.event_type, timestamp_seconds=payload.timestamp_seconds, distance_m=payload.distance_m, mscc_code=payload.mscc_code, clock_position=payload.clock_position, observation=payload.observation)
    photo: Asset | None = None
    try:
        db.add(event)
        db.flush()
        photo = _extract_photo(db, project, inspection, video, event, user, storage)
        db.add(photo)
        db.flush()
        event.photo_asset_id = photo.id
        project.report_status = "DRAFT"
        db.commit()
        db.refresh(event)
    except HTTPException:
        db.rollback()
        if photo and photo.storage_key:
            storage.delete(photo.storage_key)
        raise
    except (IntegrityError, OSError, ValueError) as exc:
        db.rollback()
        if photo and photo.storage_key:
            storage.delete(photo.storage_key)
        raise HTTPException(422, "The event or extracted frame could not be saved.") from exc
    return _event_response(event, inspection, pipe, video, photo)


@router.patch("/events/{event_id}")
def update_inspection_event(event_id: UUID, payload: InspectionEventInput, db: Session = Depends(get_db), user: User = Depends(require_roles(*EDIT_ROLES))):
    event = db.get(InspectionEvent, event_id)
    if not event:
        raise HTTPException(404, "Inspection event not found.")
    inspection, pipe, project, video = _inspection_context(db, event.inspection_id)
    section_length = pipe.survey_length_m or inspection.preset_length_m
    if section_length is not None and payload.distance_m > section_length:
        raise HTTPException(422, "Event distance cannot exceed the recorded pipe section length.")
    storage = LocalAssetStorage()
    old_photo = db.get(Asset, event.photo_asset_id) if event.photo_asset_id else None
    new_photo: Asset | None = None
    try:
        event.event_type = payload.event_type
        event.timestamp_seconds = payload.timestamp_seconds
        event.distance_m = payload.distance_m
        event.observation = payload.observation
        event.mscc_code = payload.mscc_code
        event.clock_position = payload.clock_position
        new_photo = _extract_photo(db, project, inspection, video, event, user, storage)
        db.add(new_photo)
        db.flush()
        event.photo_asset_id = new_photo.id
        project.report_status = "DRAFT"
        db.commit()
        db.refresh(event)
    except HTTPException:
        db.rollback()
        if new_photo and new_photo.storage_key:
            storage.delete(new_photo.storage_key)
        raise
    except (IntegrityError, OSError, ValueError) as exc:
        db.rollback()
        if new_photo and new_photo.storage_key:
            storage.delete(new_photo.storage_key)
        raise HTTPException(422, "The updated event or extracted frame could not be saved.") from exc
    if new_photo is None:
        raise RuntimeError("The updated defect event is missing its extracted photo")
    if old_photo:
        db.delete(old_photo)
        db.commit()
        if old_photo.storage_key:
            storage.delete(old_photo.storage_key)
    return _event_response(event, inspection, pipe, video, new_photo)


@router.delete("/events/{event_id}", status_code=204)
def delete_inspection_event(event_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles(*EDIT_ROLES))):
    event = db.get(InspectionEvent, event_id)
    if not event:
        raise HTTPException(404, "Inspection event not found.")
    photo = db.get(Asset, event.photo_asset_id) if event.photo_asset_id else None
    inspection, _, project, _ = _inspection_context(db, event.inspection_id)
    event.photo_asset_id = None
    project.report_status = "DRAFT"
    db.delete(event)
    if photo:
        db.delete(photo)
    db.commit()
    if photo and photo.storage_key:
        LocalAssetStorage().delete(photo.storage_key)
    return None


@router.get("/projects/{project_id}/site-plans")
def list_site_plans(project_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles(*READ_ROLES))):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found.")
    assets = db.scalars(select(Asset).where(Asset.project_id == project_id, Asset.file_type == "SITE_PLAN").order_by(Asset.created_at)).all()
    return {"items": [serialize(asset) for asset in assets if storage_key_exists(asset.storage_key)]}


@router.post("/projects/{project_id}/site-plans", status_code=201)
def upload_site_plan(project_id: UUID, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(require_roles(*EDIT_ROLES))):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found.")
    safe_name = _safe_file_name(file)
    extension = Path(safe_name).suffix.lower()
    expected_mime = SITE_PLAN_MIMES.get(extension)
    content_type = (file.content_type or "").lower()
    if expected_mime is None or (content_type and content_type != expected_mime):
        raise HTTPException(415, "Upload a PNG, JPEG or WebP image for the Site Layout Plan.")
    payload = file.file.read(MAX_SITE_PLAN_BYTES + 1)
    if not payload:
        raise HTTPException(422, "The Site Layout Plan file is empty.")
    if len(payload) > MAX_SITE_PLAN_BYTES:
        raise HTTPException(413, "The Site Layout Plan image exceeds the configured 25 MiB limit.")
    try:
        with Image.open(BytesIO(payload)) as image:
            image_format = image.format
            width, height = image.size
            if width < 1 or height < 1 or width * height > 40_000_000:
                raise ValueError("The Site Layout Plan image exceeds the safe pixel limit.")
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(422, "The uploaded Site Layout Plan is not a valid supported image.") from exc
    mime_from_magic = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}.get(image_format or "")
    if mime_from_magic != expected_mime:
        raise HTTPException(415, "The Site Layout Plan file type does not match its file name.")
    storage = LocalAssetStorage()
    stored = storage.save_bytes(safe_name, payload, str(project.id))
    asset = Asset(company_id=project.company_id, project_id=project.id, file_name=stored.file_name, storage_key=stored.storage_key, file_type="SITE_PLAN", mime_type=expected_mime, file_size_bytes=stored.file_size_bytes, sha256_hash=stored.sha256_hash, width_px=width, height_px=height, uploaded_by=user.id, metadata_json={"site_layout_plan": True})
    try:
        db.add(asset)
        project.report_status = "DRAFT"
        db.commit()
        db.refresh(asset)
    except (IntegrityError, OSError, ValueError) as exc:
        db.rollback()
        storage.delete(stored.storage_key)
        raise HTTPException(422, "The Site Layout Plan could not be saved.") from exc
    return serialize(asset)
