# InstaRec: Instagram Live Stream Downloader

**InstaRec** is a powerful command-line tool designed specifically to download Instagram Live streams. It captures the entire broadcast, including all available past segments from the beginning of the stream, and continues to record the live feed until it ends.

**Disclaimer:** This tool is tailored exclusively for the MPEG-DASH streams used by Instagram Live. It is **not** a generic DASH downloader and will likely fail if used with other services (like YouTube or Twitch), as it relies on the specific structure and headers of Instagram's manifests.

## Features

-   **Full Stream Archive**: Downloads all available historical segments in addition to the live stream.
-   **Interactive Mode**: Lets you choose from available video and audio quality streams.
-   **High Performance**: Utilizes `asyncio` and `aiohttp` for efficient, non-blocking downloads.
-   **Robust Error Handling**: Implements retries with exponential backoff for failed downloads.
-   **Customizable**: Offers a wide range of command-line options to control network settings, stream logic, and output.
-   **Standalone**: Relies on FFmpeg but is otherwise a self-contained Python script.

## Requirements

1.  **Python 3.8+**
2.  **FFmpeg and ffprobe:** These must be installed on your system and accessible in your system's PATH. FFmpeg is used for merging the final video file, and ffprobe is used to determine the timeline of past segments.
3.  **Python Libraries:** The tool depends on `aiofiles`, `aiohttp` and `lxml`.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd instarec
    ```

2.  **Install the required Python packages:**
    ```bash
    pip install -r requirements.txt
    ```

## How to Use

### 1. Getting the MPD URL

You need to manually obtain the manifest URL (`.mpd`) for the Instagram Live stream.

1.  Open the Instagram Live stream in a web browser (e.g., Chrome, Firefox).
2.  Open the **Developer Tools** (usually by pressing `F12` or `Ctrl+Shift+I`).
3.  Go to the **Network** tab.
4.  In the filter box, type `.mpd` to filter the network requests.
5.  You should see a request for a file ending in `.mpd`. Right-click on it and copy the full URL.

### 2. Running the Downloader

The basic command structure is:

```bash
python instarec.py [options] <mpd_url> <output_filepath>
```

#### **Example: Basic Download**

Downloads the stream using the highest available quality and saves it as `output.mkv`.

```bash
python instarec.py "https://your-copied-mpd-url/live.mpd?..." "stream_archive.mkv"
```

#### **Example: Interactive Mode**

It will first fetch all available stream qualities and prompt you to select the ones you want.

```bash
python instarec.py -i "https://your-copied-mpd-url/live.mpd?..." "stream_archive.mp4"
```

You will see a menu like this:

```
--- Available Video Streams ---
[1] ID: 720_0 | Resolution: 720x1280 | Bandwidth: 2.31 Mbps | Codecs: avc1.4D401F
[2] ID: 480_0 | Resolution: 480x854  | Bandwidth: 921.6 kbps | Codecs: avc1.4D401F
...
Select a video stream (enter number, press Enter for best):
```

### Command-Line Arguments

| Argument                  | Shorthand | Description                                                                 | Default      |
| ------------------------- | --------- | --------------------------------------------------------------------------- | ------------ |
| `mpd_url`                 |           | The URL of the .mpd manifest.                                               | (Required)   |
| `output_path`             |           | The destination filepath for the final video.                               | (Required)   |
| `--interactive`           | `-i`      | Interactively select video and audio quality from a list.                   | `False`      |
| `--verbose`               | `-v`      | Enable verbose (DEBUG level) logging.                                       | `False`      |
| `--quiet`                 | `-q`      | Suppress informational (INFO level) logging.                                | `False`      |
| `--log-file`              |           | Path to a file to write logs to.                                            | `None`       |
| `--video-quality`         |           | One or more representation IDs for video, in order of preference.           | (Highest)    |
| `--audio-quality`         |           | One or more representation IDs for audio, in order of preference.           | (Highest)    |
| `--poll-interval`         |           | Seconds to wait between polling the manifest for live segments.             | `2.0`        |
| `--max-search-requests`   |           | Max concurrent requests when searching for past segments.                   | `50`         |
| `--download-retries`      |           | Number of retries for a failed segment download.                            | `5`          |
| `--download-retry-delay`  |           | Initial delay in seconds between download retries (exponential backoff).    | `1.0`        |
| `--check-url-retries`     |           | Number of retries for a failed URL check (HEAD request).                    | `3`          |
| `--end-stream-miss-threshold` |       | Number of consecutive timestamps to search before giving up.                | `30000`      |
| `--search-chunk-size`     |           | Number of segments to check for existence in a single batch.                | `500`        |
| `--no-past`               |           | Do not download past segments; start with the live stream.                  | `False`      |
| `--keep-segments`         |           | Do not delete the temporary segments directory after finishing.             | `False`      |
| `--ffmpeg-path`           |           | Path to the ffmpeg executable.                                              | `ffmpeg`     |
| `--ffprobe-path`          |           | Path to the ffprobe executable.                                             | `ffprobe`    |