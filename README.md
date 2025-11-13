# instarec: Instagram Livestream Downloader

`instarec` is a Python-based command-line tool for downloading Instagram livestreams. It is designed to be robust, featuring concurrent downloading of video and audio segments, recovery of past segments, and automatic merging of the final video file.

## Features

-   **Interactive Quality Selection**: Interactively choose from available video and audio stream qualities.
-   **Past and Live Recording**: Downloads both previously broadcasted segments and continues to record the livestream in real-time.
-   **Optimized Performance**: Downloads segments efficiently and merges the final video without needing to re-encode.
-   **Segment Loss Detection**: Can generate a summary file detailing any missing segments from the download.
-   **Flexible Usage**: Use either a direct `.mpd` manifest URL or an Instagram username to start a download.
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

You can start a download by providing either a direct `.mpd` URL for a livestream or an Instagram username.

### Basic Examples

-   **Download from an MPD URL with interactive quality selection and mux to MKV:**
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

### Using Instagram Usernames (Requires additional setup)

To download directly from a username, you need to install an extra dependency and provide your Instagram credentials.

> [!WARNING]
> Instagram is known for flagging accounts that make automated requests. Continuously polling a user's live status **may get your account flagged or temporarily blocked**. Use this feature at your own risk.

1.  **Install `instagrapi`:**
    
    `instagrapi` is an optional dependency needed to fetch the stream URL from a username. Install it manually using pip:
    ```bash
    pip install instagrapi
    ```

2.  **Configure Credentials:**
    
    `instarec` needs your Instagram login to check a user's live status. Create a `credentials.json` file in the application's configuration directory with your username and password.
    
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

### Manually Getting the MPD URL

If you prefer not to use your credentials, you can manually find the manifest URL (`.mpd`):

1.  Open the Instagram livestream in a web browser.
2.  Open the **Developer Tools** (usually by pressing `F12` or `Ctrl+Shift+I`).
3.  Go to the **Network** tab.
4.  In the filter box, type `.mpd` to find the manifest request.
5.  Right-click the request and copy the full URL.

### Command-Line Arguments

| Argument                      | Short | Description                                                                                    |
| ----------------------------- | ----- | ---------------------------------------------------------------------------------------------- |
| `url_or_username`             |       | The URL of the .mpd manifest OR a raw Instagram username.                                      |
| `output_path`                 |       | The destination filepath for the final video. Defaults to `.mkv` if no extension is provided.  |
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
| `--no-past`                   |       | Do not download past segments, start with the livestream.                                      |
| `--end-stream-miss-threshold` |       | Number of consecutive timestamps to search before assuming the past stream has ended.          |
| `--search-chunk-size`         |       | Number of segments to check for existence in a single batch when searching.                    |
| `--live-end-timeout`          |       | Seconds to wait without a new live segment before assuming the stream has ended.               |
| `--past-segment-delay`        |       | Minimum time in seconds between each past segment download.                                    |
| `--keep-segments`             |       | Do not delete the temporary segments directory after finishing.                                |
| `--ffmpeg-path`               |       | Path to the ffmpeg executable.                                                                 |
| `--ffprobe-path`              |       | Path to the ffprobe executable.                                                                |