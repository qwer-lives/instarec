import logging
import subprocess
from pathlib import Path
from typing import List, Optional

from lxml import etree

# --- Constants ---
NS = {'mpd': 'urn:mpeg:dash:schema:mpd:2011'}


def format_bandwidth(bw: str) -> str:
    """Formats a bandwidth string into a human-readable format (kbps or Mbps)."""
    try:
        b = int(bw)
        if b > 1_000_000:
            return f"{b / 1_000_000:.2f} Mbps"
        return f"{b / 1_000:.1f} kbps"
    except (ValueError, TypeError):
        return "N/A"


def get_next_pts_from_concatenated_file(file_path: Path, ffprobe_path: str) -> Optional[int]:
    """
    Uses ffprobe to get the duration_ts of a media file, which corresponds to the
    't' value of the next segment.
    """
    log = logging.LoggerAdapter(logging.getLogger(), {'task_name': 'FFPROBE'})
    if not file_path.exists() or file_path.stat().st_size == 0:
        return None
    try:
        command = [
            ffprobe_path, '-v', 'error',
            '-show_entries', 'stream=duration_ts',
            '-of', 'default=nw=1:nk=1', str(file_path)
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return int(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as e:
        log.error(f"ffprobe failed for {file_path.name}. Error: {e}")
        return None


def select_representation(
    root: etree._Element, media_type: str, preferred_ids: Optional[List[str]]
) -> etree._Element:
    """
    Selects the best media representation from the MPD based on user preference
    or highest bandwidth.
    """
    log = logging.LoggerAdapter(logging.getLogger(), {'task_name': 'INIT'})
    media_name = media_type.split('/')[0]  # "video" or "audio"

    xpath_query = f'//mpd:Representation[@mimeType="{media_type}"]'
    all_reps = root.xpath(xpath_query, namespaces=NS)
    if not all_reps:
        raise ValueError(f"No representations found for mimeType '{media_type}'")

    # Try to find a match from the preferred IDs list
    if preferred_ids:
        for rep_id in preferred_ids:
            for rep in all_reps:
                if rep.get('id') == rep_id:
                    log.info(f"Found user-specified {media_name} representation: ID='{rep_id}', Bandwidth={rep.get('bandwidth')}")
                    return rep
        log.warning(f"None of the preferred {media_name} IDs found: {preferred_ids}. Falling back to highest bitrate.")

    # Fallback: select the representation with the highest bandwidth
    log.info(f"Selecting best {media_name} representation by highest bitrate.")
    best_rep = max(all_reps, key=lambda r: int(r.get('bandwidth', 0)))
    log.info(f"Selected {media_name} representation: ID='{best_rep.get('id')}', Bandwidth={best_rep.get('bandwidth')}")
    return best_rep