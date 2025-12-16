import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import aiohttp
from aiohttp_socks import ProxyConnector

from . import io, live, log, loss_check, merger, mpd, past


class StreamDownloader:
    def __init__(
        self,
        mpd_url: str,
        output_path_str: str,
        summary_file_path: str,
        summary_file_korean_path: str | None,
        poll_interval: float,
        max_search_requests: int,
        download_retries: int,
        download_retry_delay: float,
        check_url_retries: int,
        proxy: str | None,
        end_stream_miss_threshold: int,
        search_chunk_size: int,
        live_end_timeout: float,
        no_past: bool,
        past_segment_delay: float,
        keep_segments: bool,
        ffmpeg_path: str,
        ffprobe_path: str,
        preferred_video_ids: list[str] | None,
        preferred_audio_ids: list[str] | None,
    ):
        self.mpd_url = mpd_url
        self.base_url = mpd_url.rsplit("/", 1)[0] + "/"
        self.output_path = Path(output_path_str)
        self.segments_dir = self.output_path.with_name(self.output_path.stem + "_segments")
        self.summary_file_path = Path(summary_file_path) if summary_file_path else None
        self.summary_file_korean_path = Path(summary_file_korean_path) if summary_file_korean_path else None

        self.poll_interval = poll_interval
        self.max_search_requests = max_search_requests
        self.download_retries = download_retries
        self.download_retry_delay = download_retry_delay
        self.check_url_retries = check_url_retries
        self.proxy = proxy
        self.end_stream_miss_threshold = end_stream_miss_threshold
        self.search_chunk_size = search_chunk_size
        self.live_end_timeout = live_end_timeout
        self.no_past = no_past
        self.past_segment_delay = past_segment_delay
        self.keep_segments = keep_segments
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.preferred_video_ids = preferred_video_ids
        self.preferred_audio_ids = preferred_audio_ids

        self.video_init_path = self.segments_dir / "video_init.tmp"
        self.audio_init_path = self.segments_dir / "audio_init.tmp"
        self.video_past_path = self.segments_dir / "video_past.tmp"
        self.audio_past_path = self.segments_dir / "audio_past.tmp"
        self.video_live_path = self.segments_dir / "video_live.tmp"
        self.audio_live_path = self.segments_dir / "audio_live.tmp"

        self.session: aiohttp.ClientSession | None = None
        self.stream_info: dict[str, Any] = {}
        self.live_download_queue: asyncio.Queue[int | None] = asyncio.Queue()
        self.first_segment_t: int | None = None
        self.total_expected_segments: int = 0
        self.missing_segment_timestamps: set[int] = set()

    async def run(self):
        self.segments_dir.mkdir(parents=True, exist_ok=True)
        log.MAIN.debug(f"Temporary files will be stored in: {self.segments_dir}")
        log.MAIN.debug(f"Final output file will be: {self.output_path}")

        connector = None
        if self.proxy:
            connector = ProxyConnector.from_url(self.proxy)
            log.MAIN.debug(f"aiohttp proxy set: {self.proxy}")

        async with aiohttp.ClientSession(connector=connector) as session:
            self.session = session
            try:
                await self._fetch_initial_mpd()
                await self._download_init_segments()

                tasks = [
                    live.poll_live_manifest(self),
                    live.process_live_downloads(self),
                ]
                if not self.no_past:
                    tasks.append(past.download_past_segments(self))

                await asyncio.gather(*tasks)

            finally:
                log.MAIN.info("Download tasks finished. Proceeding to finalize video.")
                merger.finalize_video(self)
                if self.summary_file_path:
                    loss_check.create_summary_file(self)
                if self.summary_file_korean_path:
                    loss_check.create_korean_summary_file(self)

    def _raise_value_error(self, msg: str) -> None:
        raise ValueError(msg)

    async def _fetch_initial_mpd(self):
        log.INIT.debug("Fetching initial MPD manifest...")
        try:
            root, _ = await mpd.fetch_and_parse_mpd(
                self.session, self.mpd_url, self.download_retries, self.download_retry_delay
            )
            if root is None:
                self._raise_value_error("Could not fetch or parse initial manifest.")

            mpd.select_representation.preferred_video_ids = self.preferred_video_ids
            mpd.select_representation.preferred_audio_ids = self.preferred_audio_ids
            self.stream_info = mpd.parse_initial_stream_info(root, self.preferred_video_ids, self.preferred_audio_ids)

            log.INIT.debug(f"Successfully parsed MPD. Current segment t={self.stream_info['initial_t']}.")

        except (aiohttp.ClientError, ValueError):
            log.INIT.exception("Could not fetch or parse initial manifest.")
            raise

    async def _download_init_segments(self):
        log.INIT.info("Downloading initialization segments...")
        downloads = await asyncio.gather(
            io.download_file(
                self,
                urljoin(self.base_url, self.stream_info["video"]["init"]),
                [self.video_init_path, self.video_past_path],
                log.INIT,
            ),
            io.download_file(
                self,
                urljoin(self.base_url, self.stream_info["audio"]["init"]),
                [self.audio_init_path, self.audio_past_path],
                log.INIT,
            ),
        )
        if not all(downloads):
            raise RuntimeError("Failed to download one or more initialization segments. Cannot proceed.")
