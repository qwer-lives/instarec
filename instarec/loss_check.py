from pathlib import Path
from typing import TYPE_CHECKING

from . import log, utils

if TYPE_CHECKING:
    from .downloader import StreamDownloader


def _write_summary(path, content):
    try:
        with Path.open(path, "w", encoding="utf-8") as f:
            f.writelines(content)
    except OSError:
        log.SUMMARY.exception("Failed to write summary file")


def create_summary_file(downloader: "StreamDownloader"):
    log.SUMMARY.info(f"Generating summary file at: {downloader.summary_file_path}")

    content = [f"* Output File: {downloader.output_path.name}\n"]

    duration_seconds = None
    if downloader.output_path.exists():
        duration_seconds = utils.get_video_duration(downloader.output_path, downloader.ffprobe_path)

    if duration_seconds is not None:
        duration_str = utils.format_duration(duration_seconds)
        content.append(f"- Duration         : {duration_str}\n")
    else:
        content.append("- Duration         : [N/A]\n")

    if downloader.total_expected_segments == 0:
        content.append("- Status           : No segments were downloaded.\n\n")
        _write_summary(downloader.summary_file_path, content)
        return

    first_seg_str = str(downloader.first_segment_t) if downloader.first_segment_t is not None else "[N/A]"
    content.append(f"- First Segment TS   : {first_seg_str}\n")

    total_expected = downloader.total_expected_segments
    missing_segments = sorted(downloader.missing_segment_timestamps)
    miss_count = len(missing_segments)
    loss_percent = (miss_count / total_expected * 100) if total_expected > 0 else 0

    content.append(f"- Total Segments     : {total_expected} (Expected)\n")
    content.append(f"- Loss             : {miss_count}/{total_expected} ({loss_percent:.2f}%)\n")
    content.append(f"- Missing Segments   : {missing_segments}\n\n")

    _write_summary(downloader.summary_file_path, content)
