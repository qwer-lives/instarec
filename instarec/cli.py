import argparse
import asyncio
import logging
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from tqdm import tqdm

if __name__ == "__main__" and __package__ is None:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))
    from instarec import cli  # noqa: PLC0415

    sys.exit(cli.main_entry())

from . import log
from .downloader import StreamDownloader
from .interactive import interactive_stream_selection


class TqdmStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg, file=self.stream)
            self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.handleError(record)


class TaskNameFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, "task_name"):
            record.task_name = "SYSTEM"
        return True


def get_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download Instagram live streams.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    try:
        app_version = version("instarec")
    except PackageNotFoundError:
        app_version = "unknown"

    parser.add_argument("--version", action="version", version=f"%(prog)s {app_version}")

    parser.add_argument(
        "url_or_username",
        help="The URL of the .mpd manifest, a raw Instagram username, or a raw Instagram user ID (instagrapi is needed for usernames and IDs).",
    )
    parser.add_argument(
        "output_path",
        help="The destination filepath for the final video, including extension (e.g., video.mkv, video.mp4).",
    )

    parser.add_argument(
        "-i", "--interactive", action="store_true", help="Interactively select video and audio quality from a list."
    )

    auth_group = parser.add_argument_group("Authentication")
    auth_group.add_argument(
        "--cookies",
        metavar="COOKIES_FILE",
        help=(
            "Path to a Netscape-format cookie file (.txt) for Instagram authentication. "
            "Export cookies from your browser while logged into Instagram (e.g. using the "
            "'Get cookies.txt LOCALLY' extension). This is an alternative to credentials-based "
            "authentication with instagrapi."
        ),
    )

    log_group = parser.add_argument_group("Logging")
    log_group.add_argument("--log-file", help="Path to a file to write logs to.")
    log_group.add_argument("--summary-file", help="Path to a file to write a download summary to.")
    log_group.add_argument("--summary-file-korean", help="Path to a file to write a Korean download summary to.")
    verbosity_group = log_group.add_mutually_exclusive_group()
    verbosity_group.add_argument("-v", "--verbose", action="store_true", help="Enable verbose (DEBUG level) logging.")
    verbosity_group.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress informational (INFO level) logging, shows only warnings and errors.",
    )

    sel_group = parser.add_argument_group("Stream Selection")
    sel_group.add_argument(
        "--video-quality",
        nargs="+",
        help="One or more representation IDs to try for video, in order of preference. Overridden by --interactive.",
    )
    sel_group.add_argument(
        "--audio-quality",
        nargs="+",
        help="One or more representation IDs to try for audio, in order of preference. Overridden by --interactive.",
    )

    net_group = parser.add_argument_group("Network Settings")
    net_group.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds to wait between polling the manifest for live segments.",
    )
    net_group.add_argument(
        "--max-search-requests",
        type=int,
        default=50,
        help="Maximum number of concurrent requests when searching for past segments.",
    )
    net_group.add_argument(
        "--download-retries", type=int, default=5, help="Number of retries for a failed segment download."
    )
    net_group.add_argument(
        "--download-retry-delay",
        type=float,
        default=1.0,
        help="Initial delay in seconds between download retries (exponential backoff).",
    )
    net_group.add_argument(
        "--check-url-retries", type=int, default=3, help="Number of retries for a failed URL check (HEAD request)."
    )
    net_group.add_argument(
        "--proxy",
        type=str,
        default=None,
        help="Proxy URL (e.g. http://user:pass@host:port or socks5://host:port).",
    )

    stream_group = parser.add_argument_group("Stream Logic")
    stream_group.add_argument(
        "--no-past", action="store_true", help="Do not download past segments, start with the live stream."
    )
    stream_group.add_argument(
        "--end-stream-miss-threshold",
        type=int,
        default=30000,
        help="Number of consecutive timestamps to search for a segment before assuming the past stream has ended.",
    )
    stream_group.add_argument(
        "--search-chunk-size",
        type=int,
        default=500,
        help="Number of segments to check for existence in a single batch when searching.",
    )
    stream_group.add_argument(
        "--live-end-timeout",
        type=float,
        default=180.0,
        help="Seconds to wait without a new live segment before assuming the stream has ended.",
    )
    stream_group.add_argument(
        "--past-segment-delay",
        type=float,
        default=0.1,
        help="Minimum time in seconds between the start of each past segment download.",
    )

    output_group = parser.add_argument_group("Output Settings")
    output_group.add_argument(
        "--keep-segments", action="store_true", help="Do not delete the temporary segments directory after finishing."
    )
    output_group.add_argument("--ffmpeg-path", default="ffmpeg", help="Path to the ffmpeg executable.")
    output_group.add_argument("--ffprobe-path", default="ffprobe", help="Path to the ffprobe executable.")

    return parser


def configure_logging(args: argparse.Namespace):
    log_level = logging.INFO
    if args.verbose:
        log_level = logging.DEBUG
    elif args.quiet:
        log_level = logging.WARNING

    log_handlers: list[logging.Handler] = [TqdmStreamHandler()]
    if args.log_file:
        log_handlers.append(logging.FileHandler(args.log_file))

    task_filter = TaskNameFilter()
    for handler in log_handlers:
        handler.addFilter(task_filter)

    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(levelname)s - [%(task_name)s] - %(message)s", handlers=log_handlers
    )

    if not args.verbose:
        logging.getLogger("instagrapi").setLevel(logging.WARNING)
        logging.getLogger("private_request").setLevel(logging.WARNING)


async def main(args: argparse.Namespace) -> None:
    downloader = StreamDownloader(
        mpd_url=args.url_or_username,
        output_path_str=args.output_path,
        summary_file_path=args.summary_file,
        summary_file_korean_path=args.summary_file_korean,
        poll_interval=args.poll_interval,
        max_search_requests=args.max_search_requests,
        download_retries=args.download_retries,
        download_retry_delay=args.download_retry_delay,
        check_url_retries=args.check_url_retries,
        proxy=args.proxy,
        end_stream_miss_threshold=args.end_stream_miss_threshold,
        search_chunk_size=args.search_chunk_size,
        live_end_timeout=args.live_end_timeout,
        no_past=args.no_past,
        past_segment_delay=args.past_segment_delay,
        keep_segments=args.keep_segments,
        ffmpeg_path=args.ffmpeg_path,
        ffprobe_path=args.ffprobe_path,
        preferred_video_ids=args.video_quality,
        preferred_audio_ids=args.audio_quality,
    )
    await downloader.run()


def main_entry():
    parser = get_argument_parser()
    args = parser.parse_args()

    configure_logging(args)

    if not Path(args.output_path).suffix:
        args.output_path += ".mkv"
        log.MAIN.info(f"No output file extension provided. Defaulting to: {args.output_path}")

    input_value: str = args.url_or_username
    mpd_url = ""

    if "live-dash" in input_value.lower() and ".mpd" in input_value.lower():
        mpd_url = input_value
    else:
        try:
            from . import instagram  # noqa: PLC0415

            if args.cookies:
                label = f"user ID '{input_value}'" if input_value.isdigit() else f"username '{input_value}'"
                log.MAIN.info(f"Fetching live stream MPD for {label} via cookie auth...")
                client = instagram.CookieClient(cookie_file=Path(args.cookies), proxy=args.proxy)
                if input_value.isdigit():
                    mpd_url = client.get_mpd_from_user_id(input_value)
                else:
                    mpd_url = client.get_mpd_from_username(input_value)
            else:
                if input_value.isdigit():
                    log.MAIN.info(f"User ID '{input_value}' detected. Attempting to fetch live stream MPD...")
                    client = instagram.InstagramClient(proxy=args.proxy)
                    mpd_url = client.get_mpd_from_user_id(input_value)
                else:
                    log.MAIN.info(f"Username '{input_value}' detected. Attempting to fetch live stream MPD...")
                    client = instagram.InstagramClient(proxy=args.proxy)
                    mpd_url = client.get_mpd_from_username(input_value)
        except (FileNotFoundError, ValueError, instagram.UserNotLiveError, instagram.UserNotFound, instagram.CookieAuthError) as e:
            log.MAIN.error(f"Error: {e}")
            sys.exit(1)
        except Exception as e:
            log.MAIN.error(f"An unexpected error occurred during Instagram lookup: {e}")
            sys.exit(1)

    if args.interactive:
        try:
            selections = asyncio.run(interactive_stream_selection(mpd_url))
            args.video_quality = [selections["video_id"]]
            if selections["audio_id"]:
                args.audio_quality = [selections["audio_id"]]
        except (KeyboardInterrupt, asyncio.CancelledError):
            log.MAIN.warning("Stream selection cancelled by user.")
            sys.exit(0)
        except Exception as e:
            log.MAIN.error(f"Failed to fetch streams for interactive selection: {e}")
            sys.exit(1)

    args.url_or_username = mpd_url

    try:
        asyncio.run(main(args))
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.MAIN.warning("Download interrupted by user.")
    except Exception as e:
        log.MAIN.error(f"A critical error occurred: {e}", exc_info=True)
