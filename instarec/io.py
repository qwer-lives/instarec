import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import aiofiles
import aiohttp
from aiohttp.client_reqrep import CIMultiDictProxy

if TYPE_CHECKING:
    from .downloader import StreamDownloader


async def fetch_url_content(
    session: aiohttp.ClientSession,
    url: str,
    retries: int,
    retry_delay: float,
    log: logging.LoggerAdapter,
) -> tuple[bytes | None, CIMultiDictProxy | None]:
    delay = retry_delay
    for attempt in range(retries):
        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    return await response.read(), response.headers

                if response.status == 404:
                    log.warning(f"Segment not found at {url} (404 Not Found). Will not retry.")
                    return None, response.headers

                log.warning(f"Failed download attempt for {url} (Status: {response.status})")
                if 400 <= response.status < 500 and response.status != 429:
                    break

        except (TimeoutError, aiohttp.ClientError) as e:
            log.warning(f"Error downloading {url} on attempt {attempt + 1}: [{type(e).__name__}] {e}")

        if attempt < retries - 1:
            await asyncio.sleep(delay)
            delay *= 2

    log.error(f"Giving up on downloading {url} after {retries} attempts.")
    return None, None


async def download_file(downloader: "StreamDownloader", url: str, path: Path, log: logging.LoggerAdapter) -> bool:
    content, _ = await fetch_url_content(
        downloader.session, url, downloader.download_retries, downloader.download_retry_delay, log
    )
    if content:
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)
        return True
    return False


async def download_and_append_segment(
    downloader: "StreamDownloader",
    timestamp: int,
    video_path: Path,
    audio_path: Path,
    log: logging.LoggerAdapter,
) -> bool:
    video_url = urljoin(downloader.base_url, downloader.stream_info["video"]["media"].replace("$Time$", str(timestamp)))
    audio_url = urljoin(downloader.base_url, downloader.stream_info["audio"]["media"].replace("$Time$", str(timestamp)))
    results = await asyncio.gather(
        fetch_url_content(
            downloader.session, video_url, downloader.download_retries, downloader.download_retry_delay, log
        ),
        fetch_url_content(
            downloader.session, audio_url, downloader.download_retries, downloader.download_retry_delay, log
        ),
    )

    video_content, _ = results[0]
    audio_content, _ = results[1]

    if video_content and audio_content:
        log.debug(f"Downloaded segment pair for t={timestamp}")
        async with aiofiles.open(video_path, "ab") as f_vid:
            await f_vid.write(video_content)
        async with aiofiles.open(audio_path, "ab") as f_aud:
            await f_aud.write(audio_content)
        return True
    log.warning(f"Failed to download one or both segments for t={timestamp}")
    return False
