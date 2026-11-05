from __future__ import annotations

import html as html_lib
import json
import re
import subprocess
from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import _clear_login_failures, current_user, hash_password
from app.main import app
from app.models import Asset, Company, FixedReportContent, Inspection, InspectionEvent, PipeSection, Project, ReportTemplate
from app.reports import render_report_html, render_report_pdf
from app.seed import seed_demo_data
from app.storage import LocalAssetStorage


SAMPLE_FILENAMES = [
    "2026-10-27 RWSP-B2-02 to GNB (US)(DI)(150) 0.87m CCTV.mp4",
    "2026-10-27 RWSP-B2-02 to GNC (US)(DI)(100) 6.40m CCTV.mp4",
    "2026-10-27 RWSP-B2-02 to GNC (US)(DI)(100) 6.40m CCTV.mp4",
    "2026-8-28^29 Westlands Road G21 to S60 (DS)(CO)(225) 6.87m CCTV.mp4",
    "2026-8-28^29 Westlands Road S76 to G38 (US)(PVC)(150) 2.67m CCTV.mp4",
]


def _create_project(client, identities, code: str = "GENERATOR-001", **fields):
    payload = {
        "company_id": str(identities["company"].id),
        "project_code": code,
        "project_name": "Drainage Survey",
        **fields,
    }
    response = client.post("/api/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _reviewed_metadata(client, project_id: str, filenames: list[str]) -> list[dict]:
    response = client.post(f"/api/projects/{project_id}/filename-preview", json={"filenames": filenames})
    assert response.status_code == 200, response.text
    fields = (
        "file_name", "inspection_date", "survey_end_date", "start_manhole", "finish_manhole",
        "inspection_direction", "pipe_material_code", "pipe_size_mm", "survey_length_m",
        "filename_location", "source_date_label",
    )
    reviewed = [{field: item.get(field) for field in fields} for item in response.json()["items"]]
    assert all(row["inspection_date"] and row["start_manhole"] and row["finish_manhole"] for row in reviewed)
    return reviewed


def _upload_batch(client, project_id: str, filenames: list[str], payloads: list[bytes] | None = None):
    reviewed = _reviewed_metadata(client, project_id, filenames)
    data = payloads or [b"validated-upload-test-video" for _ in filenames]
    files = [("files", (name, body, "video/mp4")) for name, body in zip(filenames, data, strict=True)]
    response = client.post(
        f"/api/projects/{project_id}/survey-batch",
        data={"metadata_json": json.dumps(reviewed)},
        files=files,
    )
    return response, reviewed


def _make_short_mp4(tmp_path: Path) -> bytes:
    from imageio_ffmpeg import get_ffmpeg_exe

    path = tmp_path / "generated-cctv-test.mp4"
    command = [
        get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=12:d=2",
        "-an", "-c:v", "mpeg4", "-pix_fmt", "yuv420p", str(path),
    ]
    subprocess.run(command, check=True, capture_output=True, timeout=30)
    return path.read_bytes()


def test_company_project_pipe_and_inspection_crud(client, identities):
    company = client.post("/api/companies", json={"company_name": "Synthetic CRUD Company"})
    assert company.status_code == 201
    company_id = company.json()["id"]
    assert client.get(f"/api/companies/{company_id}").json()["company_name"] == "Synthetic CRUD Company"
    assert client.patch(f"/api/companies/{company_id}", json={"phone": "+852 1234 5678"}).json()["phone"] == "+852 1234 5678"
    assert len(client.get("/api/companies").json()["items"]) == 2

    project = _create_project(client, identities, code="CRUD-001", project_name="CRUD Demo", client_name="Sample Client", location="Test Site", report_date="2026-01-10", tv_reference_no="TV-CRUD-1")
    project_id = project["id"]
    assert client.get(f"/api/projects/{project_id}").json()["project_code"] == "CRUD-001"
    assert client.patch(f"/api/projects/{project_id}", json={"status": "IN_PROGRESS"}).json()["status"] == "IN_PROGRESS"

    pipe = client.post("/api/pipe-sections", json={"project_id": project_id, "pipe_id": "P-01", "section_reference": "MH1-MH2", "survey_length_m": 26.25, "survey_status": "COMPLETED"})
    assert pipe.status_code == 201
    pipe_id = pipe.json()["id"]
    assert client.get(f"/api/pipe-sections/{pipe_id}").json()["pipe_id"] == "P-01"
    assert client.patch(f"/api/pipe-sections/{pipe_id}", json={"remarks": "Synthetic update"}).json()["remarks"] == "Synthetic update"

    inspection = client.post("/api/inspections", json={"pipe_section_id": pipe_id, "inspection_date": "2026-01-10", "inspection_direction": "UPSTREAM", "inspection_status": "COMPLETED"})
    assert inspection.status_code == 201
    inspection_id = inspection.json()["id"]
    assert inspection.json()["inspection_number"] == 1
    assert client.get(f"/api/inspections/{inspection_id}").json()["inspection_direction"] == "UPSTREAM"
    assert client.patch(f"/api/inspections/{inspection_id}", json={"inspection_direction": "DOWNSTREAM"}).json()["inspection_direction"] == "DOWNSTREAM"
    assert client.delete(f"/api/inspections/{inspection_id}").status_code == 204
    assert client.delete(f"/api/pipe-sections/{pipe_id}").status_code == 204
    assert client.delete(f"/api/projects/{project_id}").status_code == 204
    assert client.delete(f"/api/companies/{company_id}").status_code == 204


def test_user_and_asset_crud(client, identities):
    company_id = str(identities["company"].id)
    user = client.post("/api/users", json={"company_id": company_id, "full_name": "New Operator", "email": f"new-{uuid4()}@example.test", "role": "OPERATOR"})
    assert user.status_code == 201
    user_id = user.json()["id"]
    assert client.get(f"/api/users/{user_id}").json()["role"] == "OPERATOR"
    assert client.patch(f"/api/users/{user_id}", json={"full_name": "New Operator Two"}).json()["full_name"] == "New Operator Two"
    assert client.delete(f"/api/users/{user_id}").status_code == 204
    asset = client.post("/api/assets", json={"company_id": company_id, "file_name": "sample-plan.pdf", "file_type": "PDF", "sha256_hash": "a" * 64, "metadata_json": {"synthetic": True}})
    assert asset.status_code == 201
    asset_id = asset.json()["id"]
    assert client.get(f"/api/assets/{asset_id}").json()["sha256_hash"] == "a" * 64
    assert client.patch(f"/api/assets/{asset_id}", json={"file_type": "SITE_PLAN"}).json()["file_type"] == "SITE_PLAN"
    assert client.delete(f"/api/assets/{asset_id}").status_code == 204


def test_pydantic_validation_and_viewer_rbac(client, identities):
    invalid = client.post("/api/projects", json={"project_code": "MISSING-COMPANY", "project_name": "Invalid"})
    assert invalid.status_code == 422
    app.dependency_overrides[current_user] = lambda: identities["viewer"]
    denied = client.post("/api/companies", json={"company_name": "Not allowed"})
    assert denied.status_code == 403
    assert client.get("/api/companies").status_code == 200


def test_dashboard_aggregates_seed_data(client, db: Session):
    ids = seed_demo_data(db)
    project = db.get(Project, UUID(ids["project_id"]))
    company = db.get(Company, UUID(ids["company_id"]))
    assert project is not None and company is not None
    assert project.company_id == company.id
    assert company.default_report_language == "en"
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["totals"]["projects"] == 1
    assert payload["totals"]["pipe_sections"] == 1
    assert payload["totals"]["inspections"] == 1
    assert "COMPLETED" in payload["inspections_by_status"]
    assert ids["project_id"] == payload["projects"][0]["id"]


def test_local_auth_mode_skips_manus_oauth(client, db: Session, monkeypatch):
    seed_demo_data(db)
    monkeypatch.setenv("CCTV_AUTH_MODE", "local")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CCTV_LOCAL_AUTH_EMAIL", "admin@example.test")

    with TestClient(app, client=("127.0.0.1", 8000)) as local_client:
        session = local_client.get("/api/auth/session")
        assert session.status_code == 200
        assert session.json()["authenticated"] is True
        assert session.json()["auth_mode"] == "local-demo"

        login = local_client.get("/api/auth/login", follow_redirects=False)
        assert login.status_code == 303
        assert login.headers["location"] == "/"


def test_password_auth_login_password_management_and_logout(client, db: Session, identities, monkeypatch):
    seed_demo_data(db)
    monkeypatch.setenv("CCTV_AUTH_MODE", "password")
    monkeypatch.setenv("CCTV_AUTH_SECRET", "test-only-signing-secret-with-at-least-32-characters")
    app.dependency_overrides.pop(current_user, None)
    admin = identities["admin"]
    admin.password_hash = hash_password("Correct Horse Battery! 2026")
    db.commit()
    _clear_login_failures(admin.email)
    password_client = TestClient(app, client=("127.0.0.1", 8000))

    anonymous = password_client.get("/api/auth/session")
    assert anonymous.status_code == 200
    assert anonymous.json() == {"authenticated": False, "auth_mode": "password"}
    wrong_password = password_client.post("/api/auth/login", json={"email": admin.email, "password": "incorrect password"})
    assert wrong_password.status_code == 401
    assert wrong_password.json()["detail"] == "Email or password is incorrect."

    login = password_client.post("/api/auth/login", json={"email": admin.email, "password": "Correct Horse Battery! 2026"})
    assert login.status_code == 204
    assert "httponly" in login.headers["set-cookie"].lower()
    session = password_client.get("/api/auth/session")
    assert session.status_code == 200
    assert session.json()["user"]["email"] == admin.email
    assert session.json()["auth_mode"] == "password"

    updated_password = "A Different Secure Password 2026"
    cross_origin_update = password_client.put(
        f"/api/auth/users/{identities['viewer'].id}/password",
        json={"password": updated_password},
        headers={"Origin": "https://attacker.example"},
    )
    assert cross_origin_update.status_code == 403
    update = password_client.put(f"/api/auth/users/{identities['viewer'].id}/password", json={"password": updated_password})
    assert update.status_code == 204
    listed_users = password_client.get("/api/users")
    assert listed_users.status_code == 200
    assert all("password_hash" not in row for row in listed_users.json()["items"])

    for _ in range(5):
        assert password_client.post("/api/auth/login", json={"email": admin.email, "password": "incorrect password"}).status_code == 401
    throttled = password_client.post("/api/auth/login", json={"email": admin.email, "password": "incorrect password"})
    assert throttled.status_code == 429

    logout = password_client.post("/api/auth/logout", follow_redirects=False)
    assert logout.status_code == 303
    password_client.cookies.clear()
    assert password_client.get("/api/auth/session").json() == {"authenticated": False, "auth_mode": "password"}
    _clear_login_failures(admin.email)


def test_report_contains_reference_copy_english_order_and_pdf(client, db: Session):
    ids = seed_demo_data(db)
    html = render_report_html(db, ids["project_id"])
    assert "CCTV Survey Report" in html and "Harbour View Drainage Survey" in html
    assert "This is to certify that qualified personnel have undertaken the coding for this Variation Order" in html
    assert "The machine run along the pipeline and the image is transmitted to the console unit" in html
    assert "The grading and coding in the report is referred to Manual of Sewer Condition Classification 5th Edition (MSCC (5th Edition))" not in html
    assert "The grading and coding in the report is referred to Manual of Sewer Condition Classification 5th Edition (MSCC 5th Edition)" in html
    assert "Contents</h1>" in html
    markers = (
        'id="section-cover"', 'id="section-statement"', 'id="section-contents"',
        'id="section-introduction"', 'id="section-summary"', 'id="section-appendices"',
        'id="section-appendix-i"', 'id="section-appendix-ii"', 'id="section-project-information"',
        'id="section-survey-overview"', 'id="section-section-summary"', 'id="section-detailed-section-report"',
        'id="section-defect-summary"', 'id="section-section-profile"', 'id="section-scoring-summary"',
        'id="section-survey-status"', 'id="section-appendix-iii"',
    )
    offsets = [html.index(marker) for marker in markers]
    assert offsets == sorted(offsets)
    assert "timeline-column" in html and "timeline-details" in html and "photo-sheet-table" in html
    assert not re.search(r"[\u4e00-\u9fff]", html)
    pdf = render_report_pdf(db, ids["project_id"])
    assert pdf.startswith(b"%PDF-") and len(pdf) > 4000


def test_inspection_form_has_no_removed_operator_equipment_or_status_prompts():
    resource_config = (Path(__file__).parents[2] / "frontend/src/lib/resources.ts").read_text(encoding="utf-8")
    for forbidden in ("operator_name", "vehicle", "camera", "weather", "legal_status", "inspection_status", "inspection_time"):
        assert forbidden not in resource_config
    inspection_config = resource_config.split("  inspections: {", 1)[1].split("\n  },", 1)[0]
    inspection_fields = inspection_config.split("fields:", 1)[1]
    assert "inspection_number" not in inspection_fields


def test_postgres_url_normalization():
    from app.database import normalize_database_url

    assert normalize_database_url("postgresql://user:secret@localhost/db").startswith("postgresql+psycopg://")
    assert normalize_database_url("mysql://user:secret@localhost/db").startswith("mysql+pymysql://")


def test_report_download_updates_status(client, identities):
    project = Project(company_id=identities["company"].id, project_code="PDF-001", project_name="PDF Test", report_date=date(2026, 2, 1), status="DRAFT", report_status="DRAFT")
    from app.database import get_db

    session = app.dependency_overrides[get_db]()
    session.add(project)
    session.commit()
    template = ReportTemplate(company_id=project.company_id, template_name="Test Template", is_active=True, is_default=True, language="en")
    session.add(template)
    session.flush()
    session.add(FixedReportContent(template_id=template.id, section_code="intro", title="Introduction", content_template="Sample introduction", display_order=1, version=1))
    session.commit()
    response = client.get(f"/api/projects/{project.id}/report.pdf")
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-")
    assert session.get(Project, project.id).report_status == "GENERATED"


def test_local_storage_stream_hash_and_path_safety(tmp_path):
    storage = LocalAssetStorage(tmp_path)
    saved = storage.save("frame.jpg", BytesIO(b"synthetic-frame"), "project-123")
    assert saved.file_size_bytes == 15
    assert len(saved.sha256_hash) == 64
    with storage.open(saved.storage_key) as stream:
        assert stream.read() == b"synthetic-frame"
    try:
        storage.open("../../etc/passwd")
    except ValueError:
        pass
    else:
        raise AssertionError("path traversal key was accepted")


def signed_session(email: str, open_id: str) -> str:
    import jwt
    import os

    return jwt.encode({"appId": os.environ["MANUS_PROJECT_ID"], "openId": open_id, "email": email, "name": email.split("@")[0]}, os.environ["MANUS_JWT_SECRET"], algorithm="HS256")


def test_valid_manus_session_bootstraps_first_admin_then_viewer(client, identities, monkeypatch):
    monkeypatch.delenv("CCTV_ADMIN_EMAIL", raising=False)
    monkeypatch.setenv("MANUS_PROJECT_ID", "cctv-phase-one-test")
    monkeypatch.setenv("MANUS_JWT_SECRET", "phase-one-only-test-secret")
    app.dependency_overrides.pop(current_user, None)
    client.cookies.set("webdev_app_session", signed_session("first.admin@customer.invalid", "manus-first-admin"))
    first = client.get("/api/auth/session")
    assert first.status_code == 200 and first.json()["user"]["role"] == "ADMIN"
    assert client.post("/api/companies", json={"company_name": "First Admin Company"}).status_code == 201
    client.cookies.set("webdev_app_session", signed_session("second.viewer@customer.invalid", "manus-second-viewer"))
    second = client.get("/api/auth/session")
    assert second.status_code == 200 and second.json()["user"]["role"] == "VIEWER"
    assert client.get("/api/companies").status_code == 200
    assert client.post("/api/companies", json={"company_name": "Viewer Cannot Create"}).status_code == 403


def test_configured_admin_email_prevents_first_user_privilege_escalation(client, identities, monkeypatch):
    monkeypatch.setenv("MANUS_PROJECT_ID", "cctv-phase-one-test")
    monkeypatch.setenv("MANUS_JWT_SECRET", "phase-one-only-test-secret")
    monkeypatch.setenv("CCTV_ADMIN_EMAIL", "designated.admin@customer.invalid")
    app.dependency_overrides.pop(current_user, None)
    client.cookies.set("webdev_app_session", signed_session("other.user@customer.invalid", "manus-other-user"))
    assert client.get("/api/auth/session").json()["user"]["role"] == "VIEWER"
    client.cookies.set("webdev_app_session", signed_session("designated.admin@customer.invalid", "manus-designated-admin"))
    assert client.get("/api/auth/session").json()["user"]["role"] == "ADMIN"


def test_all_five_filename_examples_batch_into_real_project_records(client, identities, db: Session):
    project = _create_project(client, identities, code="BATCH-001", project_name="Filename Import Survey")
    response, reviewed = _upload_batch(client, project["id"], SAMPLE_FILENAMES)
    assert response.status_code == 201, response.text
    assert response.json()["count"] == 5

    rows = response.json()["created"]
    assert len(rows) == 5
    assert len({row["asset_id"] for row in rows}) == 5
    assert len({row["inspection_id"] for row in rows}) == 5
    assert reviewed[3]["inspection_date"] == "2026-08-28"
    assert reviewed[3]["survey_end_date"] == "2026-08-29"
    assert reviewed[0]["inspection_direction"] == "UPSTREAM"
    assert reviewed[3]["inspection_direction"] == "DOWNSTREAM"
    assert reviewed[0]["start_manhole"] == "RWSP-B2-02"
    assert reviewed[0]["finish_manhole"] == "GNB"
    assert reviewed[0]["survey_length_m"] == "0.87"
    assert reviewed[4]["pipe_size_mm"] == "150"
    assert reviewed[3]["filename_location"] == "Westlands Road"

    project_record = db.get(Project, UUID(project["id"]))
    assert project_record is not None
    assert project_record.location is None
    assert project_record.survey_start_date == date(2026, 8, 28)
    assert project_record.survey_end_date == date(2026, 10, 27)
    assert db.scalar(select(func_count(PipeSection.id)).where(PipeSection.project_id == project_record.id)) == 4
    inspections = db.scalars(select(Inspection).join(PipeSection).where(PipeSection.project_id == project_record.id).order_by(Inspection.pipe_section_id, Inspection.inspection_number)).all()
    assert len(inspections) == 5
    assert {item.inspection_direction for item in inspections} == {"UPSTREAM", "DOWNSTREAM"}
    numbers_by_pipe: dict[object, list[int]] = {}
    for inspection in inspections:
        numbers_by_pipe.setdefault(inspection.pipe_section_id, []).append(inspection.inspection_number)
    assert sorted(sorted(numbers) for numbers in numbers_by_pipe.values()) == [[1], [1], [1], [1, 2]]
    assert all(item.video_asset_id for item in inspections)

    report_html = client.get(f"/api/projects/{project['id']}/report.html")
    assert report_html.status_code == 200
    assert "Westlands Road" in report_html.text
    assert "27/10/2026" in report_html.text
    assert "RWSP-B2-02" in report_html.text and "GNB" in report_html.text
    assert "0.87" in report_html.text and "Concrete" in report_html.text and "Ductile iron" in report_html.text
    assert not re.search(r"[\u4e00-\u9fff]", report_html.text)
    assert client.get(f"/api/projects/{project['id']}/report-data").json()["video_count"] == 5


def test_project_location_inference_requires_every_row_to_agree_and_preserves_entered_location(client, identities, db: Session):
    cases = [
        ([SAMPLE_FILENAMES[3], SAMPLE_FILENAMES[4]], None, "Westlands Road"),
        ([SAMPLE_FILENAMES[3], SAMPLE_FILENAMES[0]], None, None),
        ([SAMPLE_FILENAMES[3], "2026-8-28^29 East Shore Road S76 to G38 (US)(PVC)(150) 2.67m CCTV.mp4"], None, None),
        ([SAMPLE_FILENAMES[3], SAMPLE_FILENAMES[4]], "Location entered by the user", "Location entered by the user"),
    ]
    for filenames, entered_location, expected_location in cases:
        project = _create_project(client, identities, code=f"BATCH-LOCATION-{uuid4().hex[:8]}", location=entered_location)
        response, _ = _upload_batch(client, project["id"], filenames)
        assert response.status_code == 201, response.text
        record = db.get(Project, UUID(project["id"]))
        assert record is not None
        assert record.location == expected_location


def func_count(column):
    from sqlalchemy import func

    return func.count(column)


def test_batch_import_rejects_file_name_changed_after_review(client, identities):
    project = _create_project(client, identities, code="BATCH-MISMATCH")
    filename = SAMPLE_FILENAMES[0]
    reviewed = _reviewed_metadata(client, project["id"], [filename])
    files = [("files", ("changed-after-review.mp4", b"video-bytes", "video/mp4"))]
    response = client.post(f"/api/projects/{project['id']}/survey-batch", data={"metadata_json": json.dumps(reviewed)}, files=files)
    assert response.status_code == 422


def test_site_plan_upload_requires_real_image_and_report_embeds_it(client, identities):
    project = _create_project(client, identities, code="PLAN-001")
    output = BytesIO()
    Image.new("RGB", (320, 240), color=(25, 80, 125)).save(output, format="PNG")
    plan_bytes = output.getvalue()
    uploaded = client.post(f"/api/projects/{project['id']}/site-plans", files={"file": ("layout.png", plan_bytes, "image/png")})
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["file_type"] == "SITE_PLAN"
    assert client.get(f"/api/projects/{project['id']}/site-plans").json()["items"][0]["file_name"] == "layout.png"
    bad = client.post(f"/api/projects/{project['id']}/site-plans", files={"file": ("spoofed.png", b"not an image", "image/png")})
    assert bad.status_code == 422
    html = client.get(f"/api/projects/{project['id']}/report.html").text
    assert "layout.png" in html and "data:image/png;base64," in html


def test_batch_event_extracts_real_video_frame_and_appears_in_report(client, identities, tmp_path):
    project = _create_project(client, identities, code="EVENT-001", project_name="Video Event Survey", client_name="Water Services", client_job_reference="CLIENT-JOB-4", contractor_job_reference="CONTRACTOR-JOB-9")
    video_bytes = _make_short_mp4(tmp_path)
    response, _ = _upload_batch(client, project["id"], [SAMPLE_FILENAMES[0]], [video_bytes])
    assert response.status_code == 201, response.text
    imported = response.json()["created"][0]

    event = client.post(f"/api/inspections/{imported['inspection_id']}/events", json={
        "event_type": "DEFECT", "timestamp_seconds": 0.75, "distance_m": 0.42,
        "observation": "Joint displacement at the 11 o'clock position.",
        "clock_position": "11 o'clock", "mscc_code": "Not assigned",
    })
    assert event.status_code == 201, event.text
    details = event.json()
    assert details["video_file_name"] == SAMPLE_FILENAMES[0]
    assert details["photo_file_name"].endswith(".png")
    photo_download = client.get(details["photo_download_url"])
    assert photo_download.status_code == 200
    assert photo_download.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert client.get(f"/api/projects/{project['id']}/events").json()["items"][0]["observation"].startswith("Joint displacement")

    html = client.get(f"/api/projects/{project['id']}/report.html")
    assert html.status_code == 200
    unescaped_html = html_lib.unescape(html.text)
    for expected in ("timeline-column", "timeline-details", "photo-sheet-table", "Event 1", "0.42", "11 o'clock", "Not assigned", "CLIENT-JOB-4", "CONTRACTOR-JOB-9", "data:image/png;base64,", "Joint displacement at the 11 o'clock position."):
        assert expected in unescaped_html, expected
    assert not re.search(r"[\u4e00-\u9fff]", unescaped_html)
    pdf = client.get(f"/api/projects/{project['id']}/report.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-") and len(pdf.content) > 5000


def test_event_requires_a_real_timestamp_frame_and_respects_section_length(client, identities, tmp_path):
    project = _create_project(client, identities, code="EVENT-VALIDATION")
    response, _ = _upload_batch(client, project["id"], [SAMPLE_FILENAMES[0]], [_make_short_mp4(tmp_path)])
    assert response.status_code == 201
    inspection_id = response.json()["created"][0]["inspection_id"]
    beyond_length = client.post(f"/api/inspections/{inspection_id}/events", json={"timestamp_seconds": 0.2, "distance_m": 1.0, "observation": "Out of section length"})
    assert beyond_length.status_code == 422
    invalid_timestamp = client.post(f"/api/inspections/{inspection_id}/events", json={"timestamp_seconds": 500, "distance_m": 0.2, "observation": "No frame at this time"})
    assert invalid_timestamp.status_code in {422, 503}


def test_project_video_upload_rejects_wrong_empty_and_oversized_files(client, identities, monkeypatch):
    project = _create_project(client, identities, code="UPLOAD-CHECK")
    wrong_type = client.post(f"/api/projects/{project['id']}/videos", files={"file": ("notes.txt", b"not a video", "text/plain")})
    assert wrong_type.status_code == 415
    wrong_mime = client.post(f"/api/projects/{project['id']}/videos", files={"file": ("spoofed.mp4", b"not a video", "text/plain")})
    assert wrong_mime.status_code == 415
    empty = client.post(f"/api/projects/{project['id']}/videos", files={"file": ("empty.mp4", b"", "video/mp4")})
    assert empty.status_code == 422
    monkeypatch.setattr("app.main.MAX_VIDEO_UPLOAD_BYTES", 3)
    oversized = client.post(f"/api/projects/{project['id']}/videos", files={"file": ("large.mp4", b"1234", "video/mp4")})
    assert oversized.status_code == 413
