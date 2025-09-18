import sys
from typing import Dict, List, Optional

import aiohttp
from lxml import etree

from .utils import NS, format_bandwidth


def _display_representations(reps: List[etree._Element], media_type: str):
    print(f"\n--- Available {media_type.capitalize()} Streams ---")
    # Sort by bandwidth descending for display
    sorted_reps = sorted(reps, key=lambda r: int(r.get('bandwidth', 0)), reverse=True)
    for i, rep in enumerate(sorted_reps):
        info = [f"[{i+1}] ID: {rep.get('id', 'N/A')}"]
        if media_type == 'video':
            res = f"{rep.get('width', '?')}x{rep.get('height', '?')}"
            info.append(f"Resolution: {res}")
        info.append(f"Bandwidth: {format_bandwidth(rep.get('bandwidth'))}")
        info.append(f"Codecs: {rep.get('codecs', 'N/A')}")
        print(" | ".join(info))


def _prompt_for_selection(reps: List[etree._Element], media_type: str) -> str:
    sorted_reps = sorted(reps, key=lambda r: int(r.get('bandwidth', 0)), reverse=True)
    while True:
        try:
            choice = input(f"Select a {media_type} stream (enter number, press Enter for best): ")
            if not choice:
                selected_id = sorted_reps[0].get('id')
                print(f"Defaulting to best {media_type} stream: {selected_id}")
                return selected_id
            
            index = int(choice) - 1
            if 0 <= index < len(sorted_reps):
                selected_id = sorted_reps[index].get('id')
                print(f"Selected {media_type} stream: {selected_id}")
                return selected_id
            else:
                print(f"Invalid selection. Please enter a number between 1 and {len(sorted_reps)}.")
        except ValueError:
            print("Invalid input. Please enter a number.")
        except (KeyboardInterrupt, EOFError):
            print("\nSelection cancelled.")
            sys.exit(0)


async def interactive_stream_selection(mpd_url: str) -> Dict[str, Optional[str]]:
    """Fetches MPD and guides user through an interactive stream selection process."""
    print("Fetching stream information for interactive selection...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(mpd_url) as response:
                response.raise_for_status()
                xml_content = await response.read()
    except aiohttp.ClientError as e:
        raise RuntimeError(f"Could not fetch manifest from URL. {e}")

    root = etree.fromstring(xml_content)
    video_reps = root.xpath('//mpd:Representation[@mimeType="video/mp4"]', namespaces=NS)
    audio_reps = root.xpath('//mpd:Representation[@mimeType="audio/mp4"]', namespaces=NS)

    if not video_reps:
        raise RuntimeError("No video streams found in the manifest.")
    
    selected_video_id: Optional[str] = None
    if len(video_reps) == 1:
        selected_video_id = video_reps[0].get('id')
        print(f"\n--- Video Stream ---")
        print(f"Only one video stream found. Automatically selecting: ID='{selected_video_id}'")
    else:
        _display_representations(video_reps, "video")
        selected_video_id = _prompt_for_selection(video_reps, "video")
    
    selected_audio_id: Optional[str] = None
    if not audio_reps:
        print("\nWarning: No audio streams found in the manifest.")
    elif len(audio_reps) == 1:
        selected_audio_id = audio_reps[0].get('id')
        print(f"\n--- Audio Stream ---")
        print(f"Only one audio stream found. Automatically selecting: ID='{selected_audio_id}'")
    else:
        _display_representations(audio_reps, "audio")
        selected_audio_id = _prompt_for_selection(audio_reps, "audio")

    return {'video_id': selected_video_id, 'audio_id': selected_audio_id}