# instarec - MPEG-DASH Stream Recorder

`instarec` is a Python-based command-line tool for downloading MPEG-DASH livestreams. It is designed to capture not only the live portion of a stream but also all available past segments, allowing you to record an entire event from its very beginning.

It uses asynchronous requests for high-performance downloading and relies on FFmpeg for the final media merging process.

## Features

-   **Full Stream Archive**: Downloads all available historical segments in addition to the live stream.
-   **Interactive Mode**: Lets you choose from available video and audio quality streams.
--   **High Performance**: Utilizes `asyncio` and `aiohttp` for efficient, non-blocking downloads.
-   **Robust Error Handling**: Implements retries with exponential backoff for failed downloads.
-   **Customizable**: Offers a wide range of command-line options to control network settings, stream logic, and output.
-   **Standalone**: Relies on FFmpeg but is otherwise a self-contained Python script.

## Prerequisites

-   Python 3.7+
-   **FFmpeg** and **ffprobe**: These must be installed on your system and available in your system's PATH, or you must provide the path to the executables via command-line arguments.

## Installation

1.  **Clone the repository:**
    ```sh
    git clone <your-repository-url>
    cd instarec
    ```

2.  **Install dependencies:**
    The script relies on `aiohttp` and `lxml`. You can install them using pip.
    ```sh
    pip install aiohttp lxml
    ```

## Usage

The basic command requires the MPD manifest URL and an output file path.

```sh
python main.py <mpd_url> <output_path>
```

### Examples

**Basic Recording**
Records the stream with the highest available quality.
```sh
python main.py "https://example.com/stream.mpd" "archive.mp4"
```

**Interactive Quality Selection**
Use the `-i` flag to get a list of available video and audio streams to choose from.
```sh
python main.py -i "https://example.com/stream.mpd" "archive.mkv"
```

**Recording Live Segments Only**
To skip past segments and start recording from the live edge, use `--no-past`.
```sh
python main.py --no-past "https://example.com/stream.mpd" "live_recording.mp4"
```

**Keeping Temporary Files**
To inspect the downloaded segments, you can prevent the script from deleting the temporary `.segments` directory upon completion.
```sh
python main.py --keep-segments "https://example.com/stream.mpd" "archive.mp4"
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