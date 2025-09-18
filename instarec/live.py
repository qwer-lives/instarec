import asyncio
from typing import TYPE_CHECKING

from . import io, log, mpd
from .progress_bar import ProgressBar

if TYPE_CHECKING:
    from .downloader import StreamDownloader


async def poll_live_manifest(downloader: "StreamDownloader"):
    log.LIVE_POLL.info("Starting live manifest poller.")
    queued_live_timestamps: set[int] = set()
    last_new_segment_time: float | None = None

    while True:
        await asyncio.sleep(downloader.poll_interval)

        root, is_ended = await mpd.fetch_and_parse_mpd(
            downloader.session, downloader.mpd_url, downloader.download_retries, downloader.download_retry_delay
        )

        if is_ended:
            log.LIVE_POLL.info(
                "Stream has ended (detected 'x-fb-video-broadcast-ended' header). Shutting down live poller."
            )
            await downloader.live_download_queue.put(None)
            break

        if root is None:
            log.LIVE_POLL.warning("Failed to fetch or parse live manifest, continuing...")
            continue

        timeline = root.find(".//mpd:SegmentTimeline", namespaces=mpd.NS)
        if timeline is None:
            continue

        found_new_segment = False
        for segment in timeline.findall("mpd:S", namespaces=mpd.NS):
            t = int(segment.get("t", 0))
            if t >= downloader.stream_info["initial_t"] and t not in queued_live_timestamps:
                found_new_segment = True
                queued_live_timestamps.add(t)
                await downloader.live_download_queue.put(t)

        if found_new_segment:
            last_new_segment_time = asyncio.get_running_loop().time()
        elif last_new_segment_time is not None:
            time_since_last_segment = asyncio.get_running_loop().time() - last_new_segment_time
            if time_since_last_segment > downloader.live_end_timeout:
                log.LIVE_POLL.info(
                    f"No new segments for {time_since_last_segment:.2f}s. "
                    "Assuming stream has ended. Shutting down live poller."
                )
                await downloader.live_download_queue.put(None)
                break


async def process_live_downloads(downloader: "StreamDownloader"):
    log.LIVE_DL.info("Starting live segment downloader.")

    downloader.video_live_path.touch()
    downloader.audio_live_path.touch()

    progress_bar = ProgressBar("LIVE STREAM")
    last_live_t = downloader.stream_info["initial_t"]
    try:
        while True:
            timestamp = await downloader.live_download_queue.get()
            if timestamp is None:
                log.LIVE_DL.info("Stop signal received, ending live downloads.")
                downloader.live_download_queue.task_done()
                break

            progress_bar.update(timestamp - last_live_t)
            last_live_t = timestamp

            downloader.total_expected_segments += 1
            was_successful = await io.download_and_append_segment(
                downloader, timestamp, downloader.video_live_path, downloader.audio_live_path, log.LIVE_DL
            )
            if not was_successful:
                downloader.missing_segment_timestamps.add(timestamp)

            downloader.live_download_queue.task_done()
    finally:
        if progress_bar is not None:
            progress_bar.close()
