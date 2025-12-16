from pathlib import Path
from typing import TYPE_CHECKING

from . import log, utils

if TYPE_CHECKING:
    from .downloader import StreamDownloader


LABELS = {
    "en": {
        "filesize": "File Size",
        "duration": "Duration",
        "first_ts": "First Segment TS",
        "segments": "Total Segments",
        "loss": "Loss",
        "missing": "Missing Segments",
    },
    "ko": {
        "filesize": "로딩완료",
        "duration": "추정길이",
        "first_ts": "최초시간",
        "segments": "세그먼트",
        "loss": "손실률",
        "missing": "손실값",
    },
}


def _write_summary(path, content):
    try:
        with Path.open(path, "w", encoding="utf-8") as f:
            f.writelines(content)
    except OSError:
        log.SUMMARY.exception("Failed to write summary file")


def _generate_summary_content(downloader: "StreamDownloader", lang: str) -> list[str]:
    labels = LABELS.get(lang, LABELS["en"])
    content = [f"* {downloader.output_path.name}\n"]

    file_size_bytes = 0
    if downloader.output_path.exists():
        file_size_bytes = downloader.output_path.stat().st_size
    content.append(f"- {labels['filesize']} : {file_size_bytes:,}/{file_size_bytes:,} (100.00%)\n")

    duration_str = "00:00:00"
    duration_seconds = 0.0
    if downloader.output_path.exists():
        d = utils.get_video_duration(downloader.output_path, downloader.ffprobe_path)
        if d:
            duration_seconds = d
            duration_str = utils.format_duration(duration_seconds)
    content.append(f"- {labels['duration']} : {duration_str}\n")

    if downloader.total_expected_segments == 0:
        content.append("- Status           : No segments were downloaded.\n\n")
        return content

    first_ts = str(downloader.first_segment_t) if downloader.first_segment_t is not None else "N/A"
    content.append(f"- {labels['first_ts']} : {first_ts}\n")

    total_expected = downloader.total_expected_segments
    missing_segments = sorted(downloader.missing_segment_timestamps)
    miss_count = len(missing_segments)
    loss_percent = (miss_count / total_expected * 100) if total_expected > 0 else 0

    segment_range = f"0 ~ {total_expected - 1}" if total_expected > 0 else "0 ~ 0"

    content.append(f"- {labels['segments']} : {segment_range} ({total_expected})\n")
    content.append(f"- {labels['loss']}   : {miss_count}/{total_expected} ({loss_percent:.2f}%)\n")
    content.append(f"- {labels['missing']}   : {missing_segments}\n\n")

    return content


def create_summary_file(downloader: "StreamDownloader"):
    log.SUMMARY.info(f"Generating summary file at: {downloader.summary_file_path}")
    content = _generate_summary_content(downloader, "en")
    _write_summary(downloader.summary_file_path, content)


def create_korean_summary_file(downloader: "StreamDownloader"):
    log.SUMMARY.info(f"Generating Korean summary file at: {downloader.summary_file_korean_path}")
    content = _generate_summary_content(downloader, "ko")
    _write_summary(downloader.summary_file_korean_path, content)
