# AGENTS.md

`instarec` is a CLI tool that downloads Instagram livestreams (DASH/MPD), recovering past segments and recording the live
edge concurrently, then muxing everything with `ffmpeg` without re-encoding. See `README.md` for user-facing usage and
CLI arguments.

## Git

**Never commit** (or push, amend, or otherwise create commits). Leave all changes uncommitted in the working tree; the
maintainer reviews and commits them.

## Development

The project is managed with [uv](https://docs.astral.sh/uv/) (Python >= 3.10). `ffmpeg` and `ffprobe` must be on `PATH`.
Tools (`ruff`, `pytest`, `instarec`) live inside `.venv` and are not assumed to be on global `PATH` — always invoke them
via `uv run`.

- Setup: `uv sync --all-extras` creates `.venv/` with the project installed in editable mode, the `instagram` extra
  (`instagrapi`, `PySocks`), and the `dev` group (`pytest`, `ruff`).
- Run the local CLI: `uv run instarec <url_or_username> out.mkv` (picks up code changes without reinstalling).
- Tests: `uv run pytest` (note: `tests/test_cli.py` invokes the `instarec` script on `PATH`, so running via `uv run` is
  required).
- Lint & format: `uv run ruff check` and `uv run ruff format` (or `uv run ruff format --check`). Run both before
  finishing any change.
- Dependencies: add with `uv add <pkg>` (`--optional instagram` / `--dev` as appropriate) so `uv.lock` stays in sync;
  include the updated `uv.lock` in your changes.
- CI (`.github/workflows/test.yaml`) runs `uv sync --locked --all-extras`, `uv run instarec --help`, and
  `uv run pytest tests/` on Python 3.10–3.13. Publishing to PyPI (`publish.yml`) runs on GitHub releases or manual
  `workflow_dispatch`: runs tests first, then `uv build` and uploads via trusted publishing. The package version lives in
  `pyproject.toml`.

## Code style

**Follow the existing code style.** Match the surrounding code's naming, structure, comment density (sparse), logging
patterns, and error handling rather than introducing new conventions:

- Formatting and linting are configured in `ruff.toml`: 120-char lines, double quotes, `target-version = "py310"`, and a
  strict rule set (`__init__.py` is excluded). Key rules to keep in mind:
  - `ERA`: **No commented-out code** — delete dead code instead of commenting it out.
  - `PTH`: Use `pathlib.Path` methods (`Path.open()`, `.exists()`, `.unlink()`) instead of `os.path` or builtin `open()`.
  - `ASYNC`: Never use blocking file I/O or `time.sleep` in `async def` functions; use `aiofiles`, `asyncio.sleep`, or
    `asyncio.to_thread`.
  - `S` (`flake8-bandit`): `subprocess.run` with dynamic args in `instarec/` requires `# noqa: S603` (`tests/**` ignores
    `S101`, `S607`, `PLW1510`).
  - `TRY301`: Raising and catching an exception inside the same `try` block is flagged; use a helper or restructure.
- Modern type hints (`str | None`, `list[str]`, `dict[str, Any]`) on function signatures.
- Log through the per-task loggers in `instarec/log.py` (`MAIN`, `INIT`, `API`, `MPD`, `PAST`, `SEARCH`, `LIVE_POLL`,
  `LIVE_DL`, `MERGE`, `SUMMARY`, `FFPROBE`) with f-strings; don't create ad-hoc loggers or use `print` (except in
  `interactive.py`, which talks to the user directly).
- Core download modules (`past.py`, `live.py`, `io.py`, `merger.py`, `loss_check.py`) are collections of plain functions
  that take `downloader: "StreamDownloader"` as their first argument, importing `StreamDownloader` only under
  `if TYPE_CHECKING:` to avoid circular imports. Keep that pattern instead of adding methods or classes.
- Keep the `README.md` argument table in sync with `instarec/cli.py` when adding or changing CLI options.

## Structure

```
instarec/
  cli.py            Entry point (`instarec` script -> cli:main_entry): argparse, logging setup, MPD resolution, run
  downloader.py     StreamDownloader: holds config + shared state, orchestrates the download tasks
  mpd.py            Fetch/parse the MPD manifest (lxml), select video/audio representations
  past.py           Recover already-broadcast segments (before the first manifest's live edge)
  live.py           Poll the manifest for new segments and download them (producer/consumer via asyncio.Queue)
  io.py             HTTP fetch with retries/exponential backoff, download + append segment pairs
  merger.py         Concatenate past+live temp files, mux with ffmpeg, clean up segments dir
  loss_check.py     Optional English/Korean summary files (duration, missing segments, loss %)
  interactive.py    Interactive quality selection prompt (-i)
  progress_bar.py   tqdm wrapper styled to match log lines
  utils.py          ffprobe helpers, formatting helpers
  log.py            Named LoggerAdapters that tag records with a `task_name`
  instagram/        Resolving a username / profile URL / user ID to an MPD URL
    __init__.py     get_client(): CookieClient if --cookies, else CredentialsClient (needs the `instagram` extra)
    client.py       InstagramClient ABC: user ID resolution (HTML scraping + web_profile_info fallback via curl_cffi), get_mpd()
    cookies.py      CookieClient: Netscape cookie file (MozillaCookieJar), web API via curl_cffi
    credentials.py  CredentialsClient: instagrapi login/2FA, credentials.json & session.json in platformdirs config dir
    exceptions.py   InstagramError hierarchy (AuthError, UserNotFoundError, UserNotLiveError, MissingDependencyError)
tests/
  test_cli.py       CLI smoke tests (--help, --version) run against the installed `instarec` entry point
```

## Main flows

### 1. CLI startup (`cli.main_entry`)

1. Parse args, configure logging (`TqdmStreamHandler` so logs don't break progress bars; `TaskNameFilter` defaults
   `task_name` to `SYSTEM`; suppresses noisy `instagrapi` / `private_request` loggers unless `-v`). Default the output
   extension to `.mkv` if omitted.
2. If the input contains both `live-dash` and `.mpd`, use it directly as the MPD URL. Otherwise resolve it via
   `resolve_mpd_url` (`async with instagram.get_client(...) as client: await client.get_mpd(identifier)`); Instagram
   errors are logged and exit with status 1.
3. With `-i` / `--interactive`, `interactive_stream_selection` fetches the manifest and prompts for representation IDs,
   which override `--video-quality` / `--audio-quality`.
4. Build a `StreamDownloader` from the args and run `asyncio.run(main(args))`.

### 2. MPD resolution (`instagram.InstagramClient.get_mpd`)

Normalize the identifier (strip profile URL, `@`) → resolve a numeric user ID if needed (`fetch_user_id`) → query
`live/web_info` for `dash_abr_playback_url` → if not live, check the user's story feed `broadcast` (covers co-hosts) →
otherwise raise `UserNotLiveError`.

- **User ID resolution (`InstagramClient.fetch_user_id`)**: shared by both clients via `curl_cffi`
  (`AsyncSession(impersonate="chrome")`). Scrapes `https://www.instagram.com/{username}/` HTML for Relay JSON
  (`xig_user_by_username`) or regex ID patterns, falling back to `i.instagram.com/api/v1/users/web_profile_info/`.
- **`CookieClient` (`--cookies`)**: loads a Netscape cookie file (`MozillaCookieJar`), sets `x-csrftoken` from the
  `csrftoken` cookie, and queries the web live/story endpoints via `curl_cffi`.
- **`CredentialsClient` (default, requires `instarec[instagram]`)**: reads `username`, `password`, and optional
  `totp_seed` (`totp` / `2fa_seed`) from `--credentials` or `<user_config_dir>/instarec/credentials.json` and caches the
  session (preserving device UUIDs across re-logins) in `<user_config_dir>/instarec/session.json`. Runs blocking
  `instagrapi` calls via `asyncio.to_thread`, retries once with a full re-login on `LoginRequired`, and exposes its
  session cookies via `get_cookies()` so `InstagramClient.fetch_user_id` can use them with `curl_cffi`.

### 3. Download (`StreamDownloader.run`)

All download state lives on the `StreamDownloader` instance (`session`, `stream_info`, `live_download_queue`,
`first_segment_t`, `total_expected_segments`, `missing_segment_timestamps`), and the task modules read/mutate it. HTTP
requests during downloading use `aiohttp.ClientSession` (with `aiohttp_socks.ProxyConnector` when `--proxy` is set).

1. Create `<output_stem>_segments/` next to the output file.
2. `_fetch_initial_mpd`: parse the manifest, pick video/audio representations (preferred IDs in order, else highest
   bandwidth), and record `initial_t` (last segment timestamp = boundary between past and live) and
   `publish_frame_time`.
3. `_download_init_segments`: download the video/audio fMP4 initialization segments (`ftyp`+`moov`) into
   `video_past.tmp` / `audio_past.tmp` (always written to `*_past.tmp`, even when `--no-past` is set, so concatenating
   `*_past.tmp` + `*_live.tmp` always starts with the init header).
4. Run concurrently with `asyncio.gather`:
   - `live.poll_live_manifest`: every `--poll-interval`, fetch the MPD and queue any new segment timestamps
     `>= initial_t`. Always processes remaining segments in the manifest before stopping (pushing `None`) on the
     `x-fb-video-broadcast-ended` header or after `--live-end-timeout` seconds without new segments (once at least one
     live segment has been seen).
   - `live.process_live_downloads`: consume the queue, appending media segments (`moof`+`mdat`) to `video_live.tmp` /
     `audio_live.tmp`.
   - `past.download_past_segments` (unless `--no-past`): start at `publishFrameTime` (or forward search from 0), append
     each segment to `*_past.tmp`, and get the next timestamp from `ffprobe`'s `stream=duration_ts` on the concatenated
     `video_past.tmp`. On a missing segment or `ffprobe` failure, `search_forwards_for_next_segment` fires concurrent
     `HEAD` requests (bounded by `--max-search-requests`) in batches of `--search-chunk-size` up to
     `--end-stream-miss-threshold`.
5. `finally` (also runs on Ctrl+C or errors): `merger.finalize_video` concatenates `*_past.tmp` + `*_live.tmp` into
   `video_full.mp4` / `audio_full.mp4`, muxes them with `ffmpeg -c copy` (adding `-movflags +faststart` for `.mp4`), and
   removes the segments dir unless `--keep-segments`. Then optional English/Korean summary files (`loss_check.py`) are
   written.

Segment URLs are built by substituting `$Time$` in the representation's `SegmentTemplate@media` and joining onto the
MPD's base URL. A segment pair counts as successful only if both video and audio download.
