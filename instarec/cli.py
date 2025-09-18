import argparse
import logging
from typing import List

from .downloader import StreamDownloader


def get_argument_parser() -> argparse.ArgumentParser:
    """Creates and returns the argument parser for the application."""
    parser = argparse.ArgumentParser(
        description="Download an MPEG-DASH livestream, including all past segments.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    # --- Positional Arguments ---
    parser.add_argument("mpd_url", help="The URL of the .mpd manifest.")
    parser.add_argument("output_path", help="The destination filepath for the final video (e.g., video.mkv, video.mp4).")

    # --- Mode ---
    parser.add_argument("-i", "--interactive", action="store_true", help="Interactively select video and audio quality from a list.")

    # --- Logging ---
    log_group = parser.add_argument_group('Logging')
    log_group.add_argument("--log-file", help="Path to a file to write logs to.")
    verbosity_group = log_group.add_mutually_exclusive_group()
    verbosity_group.add_argument("-v", "--verbose", action="store_true", help="Enable verbose (DEBUG level) logging.")
    verbosity_group.add_argument("-q", "--quiet", action="store_true", help="Suppress informational (INFO level) logging, shows only warnings and errors.")

    # --- Stream Selection ---
    sel_group = parser.add_argument_group('Stream Selection')
    sel_group.add_argument("--video-quality", nargs='+', help="One or more representation IDs to try for video, in order of preference. Overridden by --interactive.")
    sel_group.add_argument("--audio-quality", nargs='+', help="One or more representation IDs to try for audio, in order of preference. Overridden by --interactive.")

    # --- Network Settings ---
    net_group = parser.add_argument_group('Network Settings')
    net_group.add_argument("--poll-interval", type=float, default=2.0, help="Seconds to wait between polling the manifest for live segments.")
    net_group.add_argument("--max-search-requests", type=int, default=50, help="Maximum number of concurrent requests when searching for past segments.")
    net_group.add_argument("--download-retries", type=int, default=5, help="Number of retries for a failed segment download.")
    net_group.add_argument("--download-retry-delay", type=float, default=1.0, help="Initial delay in seconds between download retries (exponential backoff).")
    net_group.add_argument("--check-url-retries", type=int, default=3, help="Number of retries for a failed URL check (HEAD request).")

    # --- Stream Logic ---
    stream_group = parser.add_argument_group('Stream Logic')
    stream_group.add_argument("--end-stream-miss-threshold", type=int, default=30000, help="Number of consecutive timestamps to search for a segment before assuming the past stream has ended.")
    stream_group.add_argument("--search-chunk-size", type=int, default=500, help="Number of segments to check for existence in a single batch when searching.")
    stream_group.add_argument("--no-past", action="store_true", help="Do not download past segments, start with the live stream.")

    # --- FFMpeg & Output ---
    output_group = parser.add_argument_group('Output Settings')
    output_group.add_argument("--keep-segments", action="store_true", help="Do not delete the temporary segments directory after finishing.")
    output_group.add_argument("--ffmpeg-path", default="ffmpeg", help="Path to the ffmpeg executable.")
    output_group.add_argument("--ffprobe-path", default="ffprobe", help="Path to the ffprobe executable.")
    
    return parser


def configure_logging(args: argparse.Namespace):
    """Configures the logging based on command-line arguments."""
    log_level = logging.INFO
    if args.verbose:
        log_level = logging.DEBUG
    elif args.quiet:
        log_level = logging.WARNING

    log_handlers: List[logging.Handler] = [logging.StreamHandler()]
    if args.log_file:
        log_handlers.append(logging.FileHandler(args.log_file))

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - [%(task_name)s] - %(message)s',
        handlers=log_handlers
    )


async def main(args: argparse.Namespace) -> None:
    """Initializes and runs the StreamDownloader."""
    downloader = StreamDownloader(
        mpd_url=args.mpd_url,
        output_path_str=args.output_path,
        poll_interval=args.poll_interval,
        max_search_requests=args.max_search_requests,
        download_retries=args.download_retries,
        download_retry_delay=args.download_retry_delay,
        check_url_retries=args.check_url_retries,
        end_stream_miss_threshold=args.end_stream_miss_threshold,
        search_chunk_size=args.search_chunk_size,
        no_past=args.no_past,
        keep_segments=args.keep_segments,
        ffmpeg_path=args.ffmpeg_path,
        ffprobe_path=args.ffprobe_path,
        preferred_video_ids=args.video_quality,
        preferred_audio_ids=args.audio_quality,
    )
    await downloader.run()