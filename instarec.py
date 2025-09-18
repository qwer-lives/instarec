import asyncio
import sys
from pathlib import Path

from instarec import log
from instarec.cli import configure_logging, get_argument_parser
from instarec.cli import main as cli_main
from instarec.interactive import interactive_stream_selection

SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_DIR = SCRIPT_DIR / "config"


def main():
    parser = get_argument_parser()
    args = parser.parse_args()

    configure_logging(args)

    if not Path(args.output_path).suffix:
        args.output_path += ".mkv"
        log.MAIN.info(f"No output file extension provided. Defaulting to: {args.output_path}")

    input_value = args.url_or_username
    mpd_url = ""

    if "live-dash" in input_value.lower() and ".mpd" in input_value.lower():
        mpd_url = input_value
    else:
        try:
            from instarec import instagram  # noqa: PLC0415

            log.MAIN.info(f"Username '{input_value}' detected. Attempting to fetch live stream MPD...")
            client = instagram.InstagramClient(config_dir=CONFIG_DIR)
            mpd_url = client.get_live_mpd_url(input_value)
        except (FileNotFoundError, ValueError, instagram.UserNotLiveError, instagram.UserNotFound) as e:
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
        asyncio.run(cli_main(args))
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.MAIN.warning("Download interrupted by user.")
    except Exception as e:
        log.MAIN.error(f"A critical error occurred: {e}", exc_info=True)


if __name__ == "__main__":
    main()
