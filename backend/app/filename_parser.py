from __future__ import annotations

import calendar
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

# Examples supplied by the user:
# 2026-10-27 RWSP-B2-02 to GNB (US)(DI)(150) 0.87m CCTV.mp4
# 2026-8-28^29 Westlands Road G21 to S60 (DS)(CO)(225) 6.87m CCTV.mp4
FILENAME_PATTERN = re.compile(
    r"^(?P<survey_date>20\d{2}-\d{1,2}-\d{1,2}(?:\^\d{1,2})?)\s+"
    r"(?:(?P<location>.+?)\s+)?"
    r"(?P<start_manhole>[A-Za-z0-9][A-Za-z0-9._-]*)\s+to\s+"
    r"(?P<finish_manhole>[A-Za-z0-9][A-Za-z0-9._-]*)\s+"
    r"\((?P<direction>US|DS)\)\((?P<material>[A-Za-z0-9_-]+)\)"
    r"\((?P<diameter>\d+(?:\.\d+)?)\)\s+"
    r"(?P<length>\d+(?:\.\d+)?)\s*m(?:\s+CCTV)?$",
    re.IGNORECASE,
)


def _filename_date(value: str) -> tuple[date, date]:
    start_text, separator, end_day_text = value.partition("^")
    year_text, month_text, day_text = start_text.split("-")
    start = date(int(year_text), int(month_text), int(day_text))
    if not separator:
        return start, start

    end_day = int(end_day_text)
    year, month = start.year, start.month
    last_day = calendar.monthrange(year, month)[1]
    if end_day < start.day:
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
        last_day = calendar.monthrange(year, month)[1]
    if not 1 <= end_day <= last_day:
        raise ValueError("date range end day is not valid for its month")
    return start, date(year, month, end_day)


def parse_survey_filename(file_name: str) -> dict[str, Any]:
    """Parse the filename pattern provided by the user without guessing missing values."""
    safe_name = Path(file_name.replace("\\", "/")).name
    stem = Path(safe_name).stem
    stem = re.sub(r"^\s*\d+[.)]\s*", "", stem)
    match = FILENAME_PATTERN.fullmatch(stem.strip())
    if not match:
        return {
            "file_name": safe_name,
            "parsed": False,
            "error": "Filename does not match the supported survey pattern. Review and enter the marked fields before uploading.",
            "inspection_date": None,
            "survey_end_date": None,
            "start_manhole": None,
            "finish_manhole": None,
            "inspection_direction": None,
            "material_code": None,
            "pipe_size_mm": None,
            "survey_length_m": None,
            "filename_location": None,
            "source_date_label": None,
        }

    values = match.groupdict()
    try:
        survey_start, survey_end = _filename_date(values["survey_date"])
        diameter = Decimal(values["diameter"])
        length = Decimal(values["length"])
    except (ValueError, InvalidOperation):
        return {
            "file_name": safe_name,
            "parsed": False,
            "error": "Filename contains an invalid date, diameter or survey length. Review the values before uploading.",
            "inspection_date": None,
            "survey_end_date": None,
            "start_manhole": None,
            "finish_manhole": None,
            "inspection_direction": None,
            "material_code": None,
            "pipe_size_mm": None,
            "survey_length_m": None,
            "filename_location": None,
            "source_date_label": values.get("survey_date"),
        }

    if diameter <= 0 or length < 0:
        return {
            "file_name": safe_name,
            "parsed": False,
            "error": "Pipe diameter must be positive and survey length cannot be negative.",
            "inspection_date": None,
            "survey_end_date": None,
            "start_manhole": None,
            "finish_manhole": None,
            "inspection_direction": None,
            "material_code": None,
            "pipe_size_mm": None,
            "survey_length_m": None,
            "filename_location": None,
            "source_date_label": values.get("survey_date"),
        }

    return {
        "file_name": safe_name,
        "parsed": True,
        "error": None,
        "inspection_date": survey_start.isoformat(),
        "survey_end_date": survey_end.isoformat(),
        "start_manhole": values["start_manhole"],
        "finish_manhole": values["finish_manhole"],
        "inspection_direction": "UPSTREAM" if values["direction"].upper() == "US" else "DOWNSTREAM",
        "material_code": values["material"].upper(),
        "pipe_size_mm": format(diameter.normalize(), "f"),
        "survey_length_m": format(length.normalize(), "f"),
        "filename_location": (values.get("location") or "").strip() or None,
        "source_date_label": values["survey_date"],
    }
