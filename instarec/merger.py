import shutil
import subprocess
from typing import TYPE_CHECKING

from . import log

if TYPE_CHECKING:
    from .downloader import StreamDownloader


def _parse_progress(output: str) -> dict[str, int | float]:
    values = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    parsed: dict[str, int | float] = {}
    if values.get("total_size", "N/A").isdigit():
        parsed["output_bytes"] = int(values["total_size"])
    if values.get("out_time_us", "N/A").isdigit():
        parsed["out_seconds"] = int(values["out_time_us"]) / 1_000_000
    return parsed


def finalize_video(downloader: "StreamDownloader"):
    log.MERGE.debug("Starting final merge process...")

    video_full_path = downloader.segments_dir / "video_full.mp4"
    audio_full_path = downloader.segments_dir / "audio_full.mp4"

    log.MERGE.info("Concatenating video files...")
    with video_full_path.open("wb") as f_dest:
        if downloader.video_past_path.exists():
            with downloader.video_past_path.open("rb") as f_src:
                shutil.copyfileobj(f_src, f_dest)
        if downloader.video_live_path.exists():
            with downloader.video_live_path.open("rb") as f_src:
                shutil.copyfileobj(f_src, f_dest)

    log.MERGE.info("Concatenating audio files...")
    with audio_full_path.open("wb") as f_dest:
        if downloader.audio_past_path.exists():
            with downloader.audio_past_path.open("rb") as f_src:
                shutil.copyfileobj(f_src, f_dest)
        if downloader.audio_live_path.exists():
            with downloader.audio_live_path.open("rb") as f_src:
                shutil.copyfileobj(f_src, f_dest)

    if not video_full_path.exists() or video_full_path.stat().st_size == 0:
        log.MERGE.error("No video data was downloaded. Cannot create final file.")
        return

    try:
        ffmpeg_command = [
            downloader.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_full_path),
            "-i",
            str(audio_full_path),
            "-c",
            "copy",
            "-progress",
            "pipe:1",
        ]
        if downloader.output_path.suffix.lower() == ".mp4":
            log.MERGE.info("Output is .mp4, adding '-movflags +faststart' for web compatibility.")
            ffmpeg_command.extend(["-movflags", "+faststart"])

        ffmpeg_command.extend(["-y", str(downloader.output_path.resolve())])

        log.MERGE.debug(f"Executing FFmpeg muxing: {' '.join(ffmpeg_command)}")
        result = subprocess.run(ffmpeg_command, check=True, capture_output=True)  # noqa: S603
        downloader.merge_result = {"exit_code": 0, **_parse_progress(result.stdout.decode(errors="ignore"))}
        log.MERGE.info(f"Successfully merged video to {downloader.output_path}")

        if not downloader.keep_segments:
            log.MERGE.debug(f"Cleaning up temporary directory: {downloader.segments_dir}")
            shutil.rmtree(downloader.segments_dir)
        else:
            log.MERGE.debug(f"Keeping temporary directory: {downloader.segments_dir}")

    except subprocess.CalledProcessError as e:
        downloader.merge_result = {"exit_code": e.returncode}
        log.MERGE.exception(f"FFmpeg failed to merge files. FFmpeg stderr:\n{e.stderr.decode()}\n")
    except Exception:
        log.MERGE.exception("An unexpected error occurred during merge.")
