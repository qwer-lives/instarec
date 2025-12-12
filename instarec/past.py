import asyncio
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import aiohttp

from . import io, log
from .progress_bar import ProgressBar
from .utils import get_next_pts_from_concatenated_file

if TYPE_CHECKING:
    from .downloader import StreamDownloader


async def check_url_exists(
    downloader: "StreamDownloader", url: str, timestamp: int, semaphore: asyncio.Semaphore
) -> int | None:
    async with semaphore:
        for attempt in range(downloader.check_url_retries):
            try:
                async with downloader.session.head(url, timeout=3) as response:
                    if response.status == 200:
                        return timestamp
                    if 400 <= response.status < 500 and response.status != 429:
                        return None
            except (TimeoutError, aiohttp.ClientError, RuntimeError, asyncio.CancelledError):
                if attempt == downloader.check_url_retries - 1:
                    return None
                await asyncio.sleep(0.5)
    return None


async def search_forwards_for_next_segment(downloader: "StreamDownloader", start_t: int) -> int | None:
    log.SEARCH.info(f"Searching for next segment from t={start_t}...")
    semaphore = asyncio.Semaphore(downloader.max_search_requests)
    media_template = downloader.stream_info["video"]["media"]

    all_tasks = []
    try:
        for i in range(0, downloader.end_stream_miss_threshold, downloader.search_chunk_size):
            chunk_start = start_t + i
            chunk_end = chunk_start + downloader.search_chunk_size
            log.SEARCH.debug(f"Searching in range t=[{chunk_start}, {chunk_end})...")

            chunk_tasks = [
                asyncio.create_task(
                    check_url_exists(
                        downloader, urljoin(downloader.base_url, media_template.replace("$Time$", str(t))), t, semaphore
                    )
                )
                for t in range(chunk_start, chunk_end)
            ]
            all_tasks.extend(chunk_tasks)

            for future in asyncio.as_completed(chunk_tasks):
                result = await future
                if result is not None:
                    log.SEARCH.info(f"Found first available segment at t={result}.")
                    return result
    finally:
        log.SEARCH.debug(f"Cleaning up {len(all_tasks)} search tasks.")
        for task in all_tasks:
            task.cancel()
        await asyncio.gather(*all_tasks, return_exceptions=True)

    log.SEARCH.warning(
        f"Could not find any segment after searching {downloader.end_stream_miss_threshold} timestamps from {start_t}."
    )
    return None


async def download_past_segments(downloader: "StreamDownloader"):
    log.PAST.info("Starting past segment downloader.")

    publish_frame_time = downloader.stream_info.get("publish_frame_time")
    if publish_frame_time is not None:
        log.PAST.debug(f"MPD has publishFrameTime={publish_frame_time}. Starting from here.")
        current_t = publish_frame_time
    else:
        log.PAST.info("MPD doesn't have publishFrameTime, starting search.")
        current_t = await search_forwards_for_next_segment(downloader, 0)

    if current_t is None:
        log.PAST.error("Could not find any past segments. Aborting past download task.")
        return

    progress_bar = ProgressBar("PAST STREAM", total=downloader.stream_info["initial_t"] - current_t)
    try:
        while current_t is not None and current_t < downloader.stream_info["initial_t"]:
            loop_start_time = asyncio.get_running_loop().time()
            downloader.total_expected_segments += 1

            was_successful = await io.download_and_append_segment(
                downloader, current_t, downloader.video_past_path, downloader.audio_past_path, log.PAST
            )
            if was_successful:
                if downloader.first_segment_t is None or current_t < downloader.first_segment_t:
                    downloader.first_segment_t = current_t

                next_t = get_next_pts_from_concatenated_file(downloader.video_past_path, downloader.ffprobe_path)
                if next_t is not None:
                    progress_bar.update(next_t - current_t)
                    current_t = next_t
                else:
                    log.PAST.warning(f"Could not get next PTS after t={current_t}. Searching for next segment...")
                    old_t = current_t
                    current_t = await search_forwards_for_next_segment(downloader, current_t + 1)
                    if current_t:
                        progress_bar.update(current_t - old_t)
            else:
                downloader.missing_segment_timestamps.add(current_t)
                log.PAST.warning(f"Segment at t={current_t} missing. Searching for next available...")
                old_t = current_t
                current_t = await search_forwards_for_next_segment(downloader, current_t + 1)
                if current_t:
                    progress_bar.update(current_t - old_t)

            if downloader.past_segment_delay > 0:
                elapsed_time = asyncio.get_running_loop().time() - loop_start_time
                wait_time = downloader.past_segment_delay - elapsed_time
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
    finally:
        if progress_bar is not None:
            progress_bar.close()

    log.PAST.info("Past segment download task finished.")
