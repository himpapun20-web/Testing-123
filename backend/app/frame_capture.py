from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import subprocess

import imageio_ffmpeg
from PIL import Image, UnidentifiedImageError

MAX_SOURCE_PIXELS = 40_000_000
MAX_FRAME_EDGE = 1600


@dataclass(frozen=True)
class ExtractedFrame:
    content: bytes
    width_px: int
    height_px: int
    mime_type: str = "image/png"


def extract_frame(video_path: Path, timestamp_seconds: float) -> ExtractedFrame:
    """Extract and normalize an actual frame from a stored CCTV video."""
    if timestamp_seconds < 0 or timestamp_seconds > 86_400:
        raise ValueError("Video time must be between 0 and 86,400 seconds.")
    if not video_path.is_file():
        raise ValueError("The selected CCTV video file is missing.")
    executable = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        result = subprocess.run(
            [executable, "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", f"{timestamp_seconds:.3f}", "-i", str(video_path), "-frames:v", "1", "-an", "-f", "image2pipe", "-vcodec", "png", "pipe:1"],
            check=False,
            capture_output=True,
            timeout=45,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Frame extraction exceeded the time limit.") from exc
    if result.returncode != 0 or not result.stdout:
        raise ValueError(f"No readable video frame was found at {timestamp_seconds:.3f} seconds.")
    try:
        with Image.open(BytesIO(result.stdout)) as source:
            source.load()
            if source.width * source.height > MAX_SOURCE_PIXELS:
                raise ValueError("The extracted frame exceeds the safe pixel limit.")
            image = source.convert("RGB")
            image.thumbnail((MAX_FRAME_EDGE, MAX_FRAME_EDGE), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            return ExtractedFrame(buffer.getvalue(), image.width, image.height)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("FFmpeg did not return a valid image frame.") from exc
