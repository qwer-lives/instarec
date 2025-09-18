import logging
import subprocess
from pathlib import Path
from time import gmtime, strftime

from . import log


def format_bandwidth(bw: str) -> str:
    try:
        b = int(bw)
        if b > 1_000_000:
            return f"{b / 1_000_000:.2f} Mbps"
        return f"{b / 1_000:.1f} kbps"
    except (ValueError, TypeError):
        return "N/A"


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 0:
        return "[Invalid]"
    if seconds >= 86400:
        days = seconds // 86400
        return f"{days} day(s) {strftime('%H:%M:%S', gmtime(seconds % 86400))}"
    return strftime("%H:%M:%S", gmtime(seconds))


def get_next_pts_from_concatenated_file(file_path: Path, ffprobe_path: str) -> int | None:
    if not file_path.exists() or file_path.stat().st_size == 0:
        return None
    try:
        command = [
            ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "stream=duration_ts",
            "-of",
            "default=nw=1:nk=1",
            str(file_path),
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603
        return int(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        log.FFPROBE.exception(f"ffprobe failed for {file_path.name}.")
        return None


def get_video_duration(file_path: Path, ffprobe_path: str) -> float | None:
    log = logging.LoggerAdapter(logging.getLogger(), {"task_name": "FFPROBE"})
    if not file_path.exists() or file_path.stat().st_size == 0:
        return None
    try:
        command = [
            ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        log.FFPROBE.exception(f"ffprobe failed to get duration for {file_path.name}.")
        return None
