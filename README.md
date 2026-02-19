# instarec: Instagram Livestream Downloader

`instarec` is a Python-based command-line tool for downloading Instagram livestreams. It is designed to be robust, featuring concurrent downloading of video and audio segments, recovery of past segments, and automatic merging of the final video file.

## Features

-   **Interactive Quality Selection**: Interactively choose from available video and audio stream qualities.
-   **Past and Live Recording**: Downloads both previously broadcasted segments and continues to record the livestream in real-time.
-   **Optimized Performance**: Downloads segments efficiently and merges the final video without needing to re-encode.
-   **Segment Loss Detection**: Can generate a summary file detailing any missing segments from the download.
-   **Flexible Usage**: Use a direct `.mpd` manifest URL, or provide an Instagram username and authenticate via browser cookies or credentials.
-   **Customizable**: Offers a wide range of command-line arguments to tailor the downloading process.

## Installation

### Prerequisites

You must have **`ffmpeg`** and **`ffprobe`** installed and accessible in your system's PATH. These are required for merging the final video and audio files.

### Standard Installation

The recommended way to install `instarec` is via pip:

```bash
pip install instarec
```

This will install the tool and make the `instarec` command available in your terminal.

## Usage

The simplest and most reliable way to use `instarec` is with a direct `.mpd` manifest URL. If you don't have one, `instarec` can also look it up from an Instagram username, but this requires authentication.

### Using an MPD URL (Recommended)

If you already have the `.mpd` manifest URL, no login or additional setup is needed — just pass it directly:

```bash
instarec <mpd_url> my_video.mkv
```

#### How to Get the MPD URL

1.  Open the Instagram livestream in a web browser.
2.  Open the **Developer Tools** (usually by pressing `F12` or `Ctrl+Shift+I`).
3.  Go to the **Network** tab.
4.  In the filter box, type `.mpd` to find the manifest request.
5.  Right-click the request and copy the full URL.

#### Examples

-   **With interactive quality selection:**
    ```bash
    instarec <mpd_url> my_video.mkv -i
    ```

-   **Download from an MPD URL with the best available quality and mux to MP4:**
    ```bash
    instarec <mpd_url> my_video.mp4
    ```

-   **Download with specific video/audio quality and create a summary file:**
    ```bash
    instarec <mpd_url> my_video.mkv --video-quality <video_id> --summary-file summary.txt
    ```

### Using an Instagram Username (Requires authentication)

If you don't have the `.mpd` URL, you can provide a username or user ID instead. `instarec` will log in and look up the livestream URL for you. There are two authentication methods: **cookie-based** (recommended) and **credentials-based** (instagrapi).

> [!WARNING]
> Instagram is known for flagging accounts that make automated requests. Continuously polling a user's live status **may get your account flagged or temporarily blocked**. Use this feature at your own risk.

#### Option A: Cookie-Based Authentication (Recommended)

This method uses cookies exported from your browser and does not require `instagrapi`.

1.  **Export your Instagram cookies:**

    Log into Instagram in your browser, then export your cookies as a Netscape-format `.txt` file using a browser extension such as [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc).

2.  **Pass the cookie file with `--cookies`:**
    ```bash
    instarec --cookies cookies.txt <username> my_video.mkv
    ```

If cookie auth fails (e.g. expired cookies), `instarec` will automatically fall back to credentials-based auth (Option B) if configured. On a successful fallback login, fresh cookies will be saved to the specified path for reuse next time.

#### Option B: Credentials-Based Authentication (instagrapi)

1.  **Install `instagrapi`:**

    `instagrapi` is an optional dependency needed to fetch the stream URL from a username. Install it manually using pip:
    ```bash
    pip install instagrapi
    ```

2.  **Configure Credentials:**

    Create a `credentials.json` file in the application's configuration directory with your username and password.

    The location of this directory depends on your operating system:
    *   **Linux**: `~/.config/instarec/credentials.json`
    *   **macOS**: `~/Library/Application Support/instarec/credentials.json`
    *   **Windows**: `C:\Users\<YourUser>\AppData\Local\instarec\instarec\credentials.json`

    The content of `credentials.json` should be:
    ```json
    {
      "username": "your_instagram_username",
      "password": "your_instagram_password"
    }
    ```

### Command-Line Arguments

| Argument                      | Short | Description                                                                                    |
| ----------------------------- | ----- | ---------------------------------------------------------------------------------------------- |
| `url_or_username`             |       | The URL of the .mpd manifest, a raw Instagram username, or a raw instagram user ID.            |
| `output_path`                 |       | The destination filepath for the final video. Defaults to `.mkv` if no extension is provided.  |
| `--cookies`                   |       | Path to a Netscape-format cookie file for Instagram authentication.                            |
| `--interactive`               | `-i`  | Interactively select video and audio quality.                                                  |
| `--log-file`                  |       | Path to a file to write logs to.                                                               |
| `--summary-file`              |       | Path to a file to write a download summary to.                                                 |
| `--verbose`                   | `-v`  | Enable verbose (DEBUG level) logging.                                                          |
| `--quiet`                     | `-q`  | Suppress informational (INFO level) logging.                                                   |
| `--video-quality`             |       | One or more representation IDs for video, in order of preference.                              |
| `--audio-quality`             |       | One or more representation IDs for audio, in order of preference.                              |
| `--poll-interval`             |       | Seconds to wait between polling the manifest for live segments.                                |
| `--max-search-requests`       |       | Maximum concurrent requests when searching for past segments.                                  |
| `--download-retries`          |       | Number of retries for a failed segment download.                                               |
| `--download-retry-delay`      |       | Initial delay in seconds between download retries.                                             |
| `--check-url-retries`         |       | Number of retries for a failed URL check.                                                      |
| `--proxy`                     |       | Proxy URL (e.g. http://user:pass@host:port or socks5://host:port).                             |
| `--no-past`                   |       | Do not download past segments, start with the livestream.                                      |
| `--end-stream-miss-threshold` |       | Number of consecutive timestamps to search before assuming the past stream has ended.          |
| `--search-chunk-size`         |       | Number of segments to check for existence in a single batch when searching.                    |
| `--live-end-timeout`          |       | Seconds to wait without a new live segment before assuming the stream has ended.               |
| `--past-segment-delay`        |       | Minimum time in seconds between each past segment download.                                    |
| `--keep-segments`             |       | Do not delete the temporary segments directory after finishing.                                |
| `--ffmpeg-path`               |       | Path to the ffmpeg executable.                                                                 |
| `--ffprobe-path`              |       | Path to the ffprobe executable.                                                                |
