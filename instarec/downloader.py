import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin

import aiohttp
from lxml import etree

from .utils import NS, get_next_pts_from_concatenated_file, select_representation


class StreamDownloader:
    def __init__(
        self,
        mpd_url: str,
        output_path_str: str,
        poll_interval: float,
        max_search_requests: int,
        download_retries: int,
        download_retry_delay: float,
        check_url_retries: int,
        end_stream_miss_threshold: int,
        search_chunk_size: int,
        no_past: bool,
        keep_segments: bool,
        ffmpeg_path: str,
        ffprobe_path: str,
        preferred_video_ids: Optional[List[str]],
        preferred_audio_ids: Optional[List[str]],
    ):
        self.mpd_url = mpd_url
        self.base_url = mpd_url.rsplit("/", 1)[0] + "/"
        self.output_path = Path(output_path_str)
        self.segments_dir = self.output_path.with_suffix(
            self.output_path.suffix + ".segments"
        )

        # --- Configurable parameters ---
        self.poll_interval = poll_interval
        self.max_search_requests = max_search_requests
        self.download_retries = download_retries
        self.download_retry_delay = download_retry_delay
        self.check_url_retries = check_url_retries
        self.end_stream_miss_threshold = end_stream_miss_threshold
        self.search_chunk_size = search_chunk_size
        self.no_past = no_past
        self.keep_segments = keep_segments
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.preferred_video_ids = preferred_video_ids
        self.preferred_audio_ids = preferred_audio_ids

        self.video_init_path = self.segments_dir / "video_init.m4v"
        self.audio_init_path = self.segments_dir / "audio_init.m4a"
        self.video_past_path = self.segments_dir / "video_past.tmp"
        self.audio_past_path = self.segments_dir / "audio_past.tmp"
        self.video_live_path = self.segments_dir / "video_live.tmp"
        self.audio_live_path = self.segments_dir / "audio_live.tmp"

        self.session: Optional[aiohttp.ClientSession] = None
        self.stream_info: Dict[str, Any] = {}
        self.downloaded_timestamps: Set[int] = set()
        self.live_download_queue: asyncio.Queue[Optional[int]] = asyncio.Queue()
        self.queued_live_timestamps: Set[int] = set()

    async def run(self):
        log = logging.LoggerAdapter(logging.getLogger(), {"task_name": "MAIN"})
        self.segments_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"Temporary files will be stored in: {self.segments_dir}")
        log.info(f"Final output file will be: {self.output_path}")

        async with aiohttp.ClientSession() as session:
            self.session = session
            try:
                await self._fetch_initial_mpd()
                await self._download_init_segments()

                tasks = [
                    self._poll_live_manifest(),
                    self._process_live_downloads()
                ]
                if not self.no_past:
                    tasks.append(self._download_past_segments())

                await asyncio.gather(*tasks)

            finally:
                log.info("Download tasks finished. Proceeding to finalize video.")
                self._finalize_video()

    async def _fetch_initial_mpd(self):
        log = logging.LoggerAdapter(logging.getLogger(), {'task_name': 'INIT'})
        log.info("Fetching initial MPD manifest...")
        try:
            async with self.session.get(self.mpd_url) as response:
                response.raise_for_status()
                xml_content = await response.read()
            
            root = etree.fromstring(xml_content)
            
            video_rep = select_representation(root, "video/mp4", self.preferred_video_ids)
            audio_rep = select_representation(root, "audio/mp4", self.preferred_audio_ids)

            video_template = video_rep.find('mpd:SegmentTemplate', namespaces=NS)
            audio_template = audio_rep.find('mpd:SegmentTemplate', namespaces=NS)
            last_segment = video_template.find('.//mpd:S[last()]', namespaces=NS)

            if last_segment is None:
                raise ValueError("Could not find any segments in the MPD.")

            self.stream_info = {
                'video': {'init': video_template.get('initialization'), 'media': video_template.get('media')},
                'audio': {'init': audio_template.get('initialization'), 'media': audio_template.get('media')},
                'initial_t': int(last_segment.get('t', 0))
            }
            log.info(f"Successfully parsed MPD. Initial 't' is {self.stream_info['initial_t']}.")

        except (aiohttp.ClientError, ValueError, etree.XMLSyntaxError, IndexError) as e:
            log.error(f"Could not fetch or parse initial manifest: {e}")
            raise

    async def _download_init_segments(self):
        log = logging.LoggerAdapter(logging.getLogger(), {'task_name': 'INIT'})
        log.info("Downloading initialization segments...")
        downloads = await asyncio.gather(
            self._download_file(urljoin(self.base_url, self.stream_info['video']['init']), self.video_init_path, "INIT"),
            self._download_file(urljoin(self.base_url, self.stream_info['audio']['init']), self.audio_init_path, "INIT")
        )
        if not all(downloads):
            raise RuntimeError("Failed to download one or more initialization segments. Cannot proceed.")

    async def _fetch_url_content(self, url: str, task_name: str) -> Optional[bytes]:
        log = logging.LoggerAdapter(logging.getLogger(), {'task_name': task_name})
        delay = self.download_retry_delay
        for attempt in range(self.download_retries):
            try:
                async with self.session.get(url, timeout=10) as response:
                    if response.status == 200:
                        return await response.read()
                    
                    log.warning(f"Failed download attempt for {url} (Status: {response.status})")
                    if 400 <= response.status < 500 and response.status != 429:
                        break
            
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                log.warning(f"Error downloading {url} on attempt {attempt + 1}: {e}")

            if attempt < self.download_retries - 1:
                await asyncio.sleep(delay)
                delay *= 2
        
        log.error(f"Giving up on downloading {url} after {self.download_retries} attempts.")
        return None

    async def _download_file(self, url: str, path: Path, task_name: str) -> bool:
        content = await self._fetch_url_content(url, task_name)
        if content:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'wb') as f:
                f.write(content)
            return True
        return False

    async def _check_url_exists(self, url: str, timestamp: int, semaphore: asyncio.Semaphore) -> Optional[int]:
        async with semaphore:
            for attempt in range(self.check_url_retries):
                try:
                    async with self.session.head(url, timeout=3) as response:
                        if response.status == 200:
                            return timestamp
                        if 400 <= response.status < 500 and response.status != 429:
                           return None
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    if attempt == self.check_url_retries - 1:
                        return None
                    await asyncio.sleep(0.5)
        return None

    async def _search_forwards_for_next_segment(self, start_t: int) -> Optional[int]:
        log = logging.LoggerAdapter(logging.getLogger(), {'task_name': 'SEARCH'})
        log.info(f"Searching for next segment from t={start_t}...")
        semaphore = asyncio.Semaphore(self.max_search_requests)
        media_template = self.stream_info['video']['media']

        for i in range(0, self.end_stream_miss_threshold, self.search_chunk_size):
            chunk_start = start_t + i
            chunk_end = chunk_start + self.search_chunk_size
            log.info(f"Searching in range t=[{chunk_start}, {chunk_end})...")
            
            tasks = [
                asyncio.create_task(self._check_url_exists(
                    urljoin(self.base_url, media_template.replace('$Time$', str(t))),
                    t,
                    semaphore
                )) for t in range(chunk_start, chunk_end)
            ]

            try:
                for future in asyncio.as_completed(tasks):
                    result = await future
                    if result is not None:
                        log.info(f"Found first available segment at t={result}.")
                        # Cancel remaining tasks to stop searching
                        for task in tasks:
                            task.cancel()
                        return result
            except asyncio.CancelledError:
                pass # Expected when a result is found
            finally:
                # Ensure all tasks are cleaned up
                for task in tasks:
                    if not task.done():
                        task.cancel()


        log.warning(f"Could not find any segment after searching {self.end_stream_miss_threshold} timestamps from {start_t}.")
        return None

    async def _download_and_append_segment(self, timestamp: int, video_path: Path, audio_path: Path, task_name: str):
        log = logging.LoggerAdapter(logging.getLogger(), {'task_name': task_name})
        
        video_url = urljoin(self.base_url, self.stream_info['video']['media'].replace('$Time$', str(timestamp)))
        audio_url = urljoin(self.base_url, self.stream_info['audio']['media'].replace('$Time$', str(timestamp)))
        video_content, audio_content = await asyncio.gather(
            self._fetch_url_content(video_url, task_name),
            self._fetch_url_content(audio_url, task_name)
        )

        if video_content and audio_content:
            log.info(f"Downloaded segment pair for t={timestamp}")
            self.downloaded_timestamps.add(timestamp)
            with open(video_path, "ab") as f_vid:
                f_vid.write(video_content)
            with open(audio_path, "ab") as f_aud:
                f_aud.write(audio_content)
            return True
        else:
            log.warning(f"Failed to download one or both segments for t={timestamp}")
            return False

    async def _download_past_segments(self):
        log = logging.LoggerAdapter(logging.getLogger(), {'task_name': 'PAST'})
        log.info("Starting past segment downloader.")
        
        shutil.copyfile(self.video_init_path, self.video_past_path)
        shutil.copyfile(self.audio_init_path, self.audio_past_path)

        current_t = await self._search_forwards_for_next_segment(0)
        if current_t is None:
            log.error("Could not find any past segments. Aborting past download task.")
            return

        while current_t is not None and current_t < self.stream_info['initial_t']:
            if await self._download_and_append_segment(current_t, self.video_past_path, self.audio_past_path, "PAST"):
                next_t = get_next_pts_from_concatenated_file(self.video_past_path, self.ffprobe_path)
                if next_t is not None:
                    current_t = next_t
                else:
                    log.warning(f"Could not get next PTS after t={current_t}. Searching for next segment...")
                    current_t = await self._search_forwards_for_next_segment(current_t + 1)
            else:
                log.warning(f"Segment at t={current_t} missing. Searching for next available...")
                current_t = await self._search_forwards_for_next_segment(current_t + 1)

        log.info("Past segment download task finished.")

    async def _poll_live_manifest(self):
        log = logging.LoggerAdapter(logging.getLogger(), {'task_name': 'LIVE-POLL'})
        log.info("Starting live manifest poller.")

        while True:
            await asyncio.sleep(self.poll_interval)
            try:
                async with self.session.get(self.mpd_url) as response:
                    if "x-fb-video-broadcast-ended" in response.headers or response.status != 200:
                        log.info("Broadcast ended or MPD unavailable. Shutting down live poller.")
                        await self.live_download_queue.put(None)
                        break
                    xml_content = await response.read()
                    root = etree.fromstring(xml_content)
            except Exception as e:
                log.warning(f"Failed to fetch live manifest: {e}")
                continue

            timeline = root.find('.//mpd:SegmentTimeline', namespaces=NS)
            if timeline is None:
                continue

            for segment in timeline.findall('mpd:S', namespaces=NS):
                t = int(segment.get('t', 0))
                if t >= self.stream_info['initial_t'] and t not in self.queued_live_timestamps:
                    self.queued_live_timestamps.add(t)
                    await self.live_download_queue.put(t)

    async def _process_live_downloads(self):
        log = logging.LoggerAdapter(logging.getLogger(), {'task_name': 'LIVE-DL'})
        log.info("Starting live segment downloader.")

        self.video_live_path.touch()
        self.audio_live_path.touch()
        
        while True:
            timestamp = await self.live_download_queue.get()
            if timestamp is None: # Sentinel received
                log.info("Stop signal received, ending live downloads.")
                self.live_download_queue.task_done()
                break
            
            await self._download_and_append_segment(
                timestamp, self.video_live_path, self.audio_live_path, "LIVE-DL"
            )
            self.live_download_queue.task_done()

    def _finalize_video(self):
        log = logging.LoggerAdapter(logging.getLogger(), {'task_name': 'MERGE'})
        log.info("Starting final merge process...")

        video_full_path = self.segments_dir / "video_full.mp4"
        audio_full_path = self.segments_dir / "audio_full.mp4"
        
        log.info("Concatenating video files...")
        with open(video_full_path, 'wb') as f_dest:
            if self.video_past_path.exists():
                with open(self.video_past_path, 'rb') as f_src: shutil.copyfileobj(f_src, f_dest)
            if self.video_live_path.exists():
                with open(self.video_live_path, 'rb') as f_src: shutil.copyfileobj(f_src, f_dest)
        
        log.info("Concatenating audio files...")
        with open(audio_full_path, 'wb') as f_dest:
            if self.audio_past_path.exists():
                with open(self.audio_past_path, 'rb') as f_src: shutil.copyfileobj(f_src, f_dest)
            if self.audio_live_path.exists():
                with open(self.audio_live_path, 'rb') as f_src: shutil.copyfileobj(f_src, f_dest)
        
        if not video_full_path.exists() or video_full_path.stat().st_size == 0:
            log.error("No video data was downloaded. Cannot create final file.")
            return

        try:
            ffmpeg_command = [
                self.ffmpeg_path, '-hide_banner', '-loglevel', 'error',
                '-i', str(video_full_path),
                '-i', str(audio_full_path),
                '-c', 'copy',
            ]
            if self.output_path.suffix.lower() == '.mp4':
                log.info("Output is .mp4, adding '-movflags +faststart' for web compatibility.")
                ffmpeg_command.extend(['-movflags', '+faststart'])

            ffmpeg_command.extend(['-y', str(self.output_path.resolve())])

            log.info(f"Executing FFmpeg muxing: {' '.join(ffmpeg_command)}")
            result = subprocess.run(ffmpeg_command, check=True, capture_output=True)
            log.info(f"Successfully merged video to {self.output_path}")

            if not self.keep_segments:
                log.info(f"Cleaning up temporary directory: {self.segments_dir}")
                shutil.rmtree(self.segments_dir)
            else:
                log.info(f"Keeping temporary directory: {self.segments_dir}")

        except subprocess.CalledProcessError as e:
            log.error("FFmpeg failed to merge files.")
            log.error(f"FFmpeg stderr:\n{e.stderr.decode()}")
            log.error(f"Temporary files are kept in '{self.segments_dir}' for inspection.")
        except Exception as e:
            log.error(f"An unexpected error occurred during merge: {e}")
            log.error(f"Temporary files are kept in '{self.segments_dir}' for inspection.")