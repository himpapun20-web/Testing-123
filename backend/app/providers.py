from __future__ import annotations

from typing import Any, Protocol


class BackgroundJobQueue(Protocol):
    """Integration boundary for the later video-analysis job worker."""
    def enqueue(self, job_type: str, payload: dict[str, Any]) -> str: ...


class OCRProvider(Protocol):
    def extract(self, asset_key: str, *, model_version: str) -> dict[str, Any]: ...


class VisionProvider(Protocol):
    def analyze_frame(self, asset_key: str, *, model_version: str, prompt_version: str) -> dict[str, Any]: ...


class ConditionScorer(Protocol):
    """Deterministic rule engine contract; no free-text model grade is authoritative."""
    def score(self, events: list[dict[str, Any]], rules: dict[str, Any]) -> dict[str, Any]: ...
