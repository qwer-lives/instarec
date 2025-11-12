# instarec: Instagram livestream downloader

`instarec` is a Python-based command-line tool for downloading Instagram livestreams. It is designed to be robust, featuring concurrent downloading of video and audio segments, recovery of past segments, and automatic merging of the final video file.

## Features

- **Download from MPD or Username**: Start a download using either a direct MPD manifest URL or an Instagram username.
- **Interactive Quality Selection**: Interactively choose from available video and audio stream qualities.
- **Past and Live Recording**: Downloads both previously broadcasted segments and continues to record the livestream.
- **Optimized**: No exhaustive search except when needed (a segment is lost), merge of segments is performed as livestream is diwonloaded. 
- **Segment Loss Detection**: Generates a summary file detailing any missing segments from the download.
- **Customizable**: Offers a wide range of command-line arguments to tailor the downloading process.

## Setup and Installation

### Basic Setup (MPD URL only)

For downloading directly from an MPD manifest URL, you only need to install the Python dependencies listed in `requirements.txt`.

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd instarec
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

### Instagram Username Setup

To download using an Instagram username, you'll need to install `instagrapi` and configure your Instagram credentials.

1.  **Install `instagrapi`:**

    It's recommended to install `instagrapi` with `--no-deps` to avoid potential conflicts with older dependencies.
    ```bash
    pip install -r requirements_instagrapi.txt --no-deps
    ```

2.  **Configure Credentials:**

    Set your username and password in `config/credentials.json`:

    ```json
    {
      "username": "your_instagram_username",
      "password": "your_instagram_password"
    }
    ```

    **Important Note on Polling:** Avoid using the username feature to continuously poll for a user going live. Instagram may flag your account for bot-like activity. This feature is intended for when you already know a user is live.

## Usage

The script can be run from the command line with various arguments.

### Getting the MPD URL

You can manually obtain the manifest URL (`.mpd`) for an Instagram livestream:

1.  Open the Instagram livestream in a web browser (e.g., Chrome, Firefox).
2.  Open the **Developer Tools** (usually by pressing `F12` or `Ctrl+Shift+I`).
3.  Go to the **Network** tab.
4.  In the filter box, type `.mpd` to filter the network requests.
5.  You should see a request for a file ending in `.mpd`. Right-click on it and copy the full URL.

### Basic Examples

-   **Download from an Instagram Username (Interactive Quality Selection):**
    ```bash
    python instarec.py <username> <output_file.mkv> -i
    ```

-   **Download from an MPD URL with the best detected quality (based on bitrate):**
    ```bash
    python instarec.py <mpd_url> <output_file.mp4>
    ```

-   **Download from an MPD URL with specific video and audio quality:**
    ```bash
    python instarec.py <mpd_url> <output_file.mp4> --video-quality <video_id> --audio-quality <audio_id>
    ```

### Command-Line Arguments

| Argument | Short | Description |
|---|---|---|
| `url_or_username` | | The URL of the .mpd manifest OR a raw Instagram username. |
| `output_path` | | The destination filepath for the final video. |
| `--interactive` | `-i` | Interactively select video and audio quality. |
| `--log-file` | | Path to a file to write logs to. |
| `--summary-file` | | Path to a file to write a download summary to. |
| `--verbose` | `-v` | Enable verbose (DEBUG level) logging. |
| `--quiet` | `-q` | Suppress informational (INFO level) logging. |
| `--video-quality` | | One or more representation IDs for video, in order of preference. |
| `--audio-quality` | | One or more representation IDs for audio, in order of preference. |
| `--poll-interval` | | Seconds to wait between polling the manifest for live segments. |
| `--max-search-requests` | | Maximum concurrent requests when searching for past segments. |
| `--download-retries` | | Number of retries for a failed segment download. |
| `--download-retry-delay`| | Initial delay in seconds between download retries. |
| `--check-url-retries` | | Number of retries for a failed URL check. |
| `--no-past` | | Do not download past segments, start with the livestream. |
| `--end-stream-miss-threshold` | | Number of consecutive timestamps to search before assuming the past stream has ended. |
| `--search-chunk-size` | | Number of segments to check for existence in a single batch when searching. |
| `--live-end-timeout` | | Seconds to wait without a new live segment before assuming the stream has ended. |
| `--past-segment-delay` | | Minimum time in seconds between each past segment download. |
| `--keep-segments` | | Do not delete the temporary segments directory after finishing. |
| `--ffmpeg-path` | | Path to the ffmpeg executable. |
| `--ffprobe-path` | | Path to the ffprobe executable. |