import argparse
import asyncio
import logging
import sys

from instarec.cli import main as cli_main
from instarec.cli import configure_logging, get_argument_parser
from instarec.interactive import interactive_stream_selection


def main():
    """Main entry point for the application."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # --- Interactive Mode Handling ---
    if args.interactive:
        try:
            selections = asyncio.run(interactive_stream_selection(args.mpd_url))
            args.video_quality = [selections['video_id']]
            if selections['audio_id']:
                args.audio_quality = [selections['audio_id']]
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\nStream selection cancelled by user.")
            sys.exit(0)
        except Exception as e:
            print(f"Failed to fetch streams for interactive selection: {e}", file=sys.stderr)
            sys.exit(1)

    # --- Configure Logging ---
    configure_logging(args)

    # --- Run Main Application ---
    try:
        asyncio.run(cli_main(args))
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nDownload interrupted by user.")
    except Exception as e:
        logging.getLogger().critical(f"A critical error occurred: {e}", exc_info=True)


if __name__ == '__main__':
    main()