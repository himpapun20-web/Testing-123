from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CompanyInput(InputModel):
    company_name: str = Field(min_length=2, max_length=255)
    registration_no: str | None = Field(default=None, max_length=100)
    logo_asset_id: UUID | None = None
    address_line_1: str | None = Field(default=None, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    fax: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=255)
    default_report_language: str = Field(default="en", max_length=20)


class UserInput(InputModel):
    company_id: UUID
    full_name: str = Field(min_length=2, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    role: Literal["ADMIN", "PROJECT_MANAGER", "OPERATOR", "VIEWER", "AI_SERVICE"] = "VIEWER"
    signature_asset_id: UUID | None = None
    eusr_certificate_no: str | None = Field(default=None, max_length=100)
    is_active: bool = True


class ProjectInput(InputModel):
    company_id: UUID
    project_code: str = Field(min_length=1, max_length=100)
    project_name: str = Field(min_length=2, max_length=255)
    project_description: str | None = None
    client_name: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    report_date: date | None = None
    survey_start_date: date | None = None
    survey_end_date: date | None = None
    tv_reference_no: str | None = Field(default=None, max_length=100)
    client_job_reference: str | None = Field(default=None, max_length=100)
    contractor_job_reference: str | None = Field(default=None, max_length=100)
    contractor_name: str | None = Field(default=None, max_length=255)
    project_manager_name: str | None = Field(default=None, max_length=255)
    project_manager_user_id: UUID | None = None
    eusr_certificate_no: str | None = Field(default=None, max_length=100)
    status: Literal["DRAFT", "IN_PROGRESS", "COMPLETED", "ON_HOLD"] = "DRAFT"
    report_status: Literal["NOT_GENERATED", "DRAFT", "GENERATED", "FINALIZED"] = "NOT_GENERATED"


class PipeSectionInput(InputModel):
    project_id: UUID
    pipe_id: str = Field(min_length=1, max_length=100)
    section_reference: str = Field(min_length=1, max_length=100)
    start_manhole: str | None = Field(default=None, max_length=100)
    finish_manhole: str | None = Field(default=None, max_length=100)
    function_code: str | None = Field(default=None, max_length=20)
    function_description: str | None = Field(default=None, max_length=100)
    survey_length_m: Decimal | None = Field(default=None, ge=0, le=100000)
    pipe_size_mm: Decimal | None = Field(default=None, gt=0, le=100000)
    pipe_shape: str | None = Field(default=None, max_length=100)
    pipe_material_code: str | None = Field(default=None, max_length=50)
    pipe_material_description: str | None = Field(default=None, max_length=255)
    survey_status: Literal["NOT_SURVEYED", "IN_PROGRESS", "COMPLETED", "PARTIAL", "ABANDONED"] = "NOT_SURVEYED"
    survey_abandoned_reason: str | None = None
    remarks: str | None = None
    condition_grade: Decimal | None = Field(default=None, ge=0, le=5)
    recommendation: str | None = None
    start_level_m: Decimal | None = None
    finish_level_m: Decimal | None = None
    geometry_json: dict[str, Any] | None = None


class AssetInput(InputModel):
    company_id: UUID
    project_id: UUID | None = None
    file_name: str = Field(min_length=1, max_length=255)
    storage_key: str | None = None
    file_url: str | None = None
    file_type: Literal["LOGO", "SIGNATURE", "VIDEO", "PHOTO", "SITE_PLAN", "SPREADSHEET", "PDF", "OTHER"] = "OTHER"
    mime_type: str | None = Field(default=None, max_length=100)
    file_size_bytes: int | None = Field(default=None, ge=0)
    sha256_hash: str | None = Field(default=None, pattern=r"^[A-Fa-f0-9]{64}$")
    width_px: int | None = Field(default=None, ge=1)
    height_px: int | None = Field(default=None, ge=1)
    duration_seconds: Decimal | None = Field(default=None, ge=0)
    metadata_json: dict[str, Any] | None = None


class InspectionInput(InputModel):
    pipe_section_id: UUID
    video_asset_id: UUID | None = None
    inspection_number: int | None = Field(default=None, ge=1)
    inspection_date: date | None = None
    inspection_time: time | None = None
    inspection_direction: Literal["FORWARD", "REVERSE", "UPSTREAM", "DOWNSTREAM"] = "DOWNSTREAM"
    operator_name: str | None = Field(default=None, max_length=255)
    vehicle: str | None = Field(default=None, max_length=100)
    camera: str | None = Field(default=None, max_length=100)
    preset_length_m: Decimal | None = Field(default=None, ge=0)
    weather: str | None = Field(default=None, max_length=100)
    pre_cleaned: str | None = Field(default=None, max_length=100)
    legal_status: str | None = Field(default=None, max_length=100)
    upstream_pipe_depth_m: Decimal | None = Field(default=None, ge=0)
    downstream_pipe_depth_m: Decimal | None = Field(default=None, ge=0)
    inspection_status: Literal["SCHEDULED", "IN_PROGRESS", "COMPLETED", "PARTIAL", "ABANDONED", "FAILED"] = "SCHEDULED"


class FilenamePreviewInput(InputModel):
    filenames: list[str] = Field(min_length=1, max_length=50)


class SurveyFileMetadata(InputModel):
    file_name: str = Field(min_length=1, max_length=255)
    inspection_date: date
    survey_end_date: date | None = None
    start_manhole: str = Field(min_length=1, max_length=100)
    finish_manhole: str = Field(min_length=1, max_length=100)
    inspection_direction: Literal["UPSTREAM", "DOWNSTREAM"]
    pipe_material_code: str | None = Field(default=None, max_length=50)
    pipe_size_mm: Decimal | None = Field(default=None, gt=0, le=100000)
    survey_length_m: Decimal = Field(ge=0, le=100000)
    filename_location: str | None = Field(default=None, max_length=255)
    source_date_label: str | None = Field(default=None, max_length=40)


class InspectionEventInput(InputModel):
    event_type: Literal["DEFECT", "START_NODE", "WATER_LEVEL", "GENERAL_PHOTO", "FINISH_NODE", "SITE_PHOTO"] = "DEFECT"
    timestamp_seconds: Decimal = Field(ge=0, le=86400)
    distance_m: Decimal = Field(ge=0, le=100000)
    observation: str = Field(min_length=1, max_length=2000)
    mscc_code: str | None = Field(default=None, max_length=50)
    clock_position: str | None = Field(default=None, max_length=30)


INPUT_SCHEMAS = {
    "companies": CompanyInput,
    "users": UserInput,
    "projects": ProjectInput,
    "pipe-sections": PipeSectionInput,
    "assets": AssetInput,
    "inspections": InspectionInput,
}
