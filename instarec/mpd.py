from typing import Any

import aiohttp
from lxml import etree

from . import io, log, utils

NS = {"mpd": "urn:mpeg:dash:schema:mpd:2011"}


def _format_rep_info(rep: etree._Element, media_name: str) -> str:
    info_parts = [f"ID='{rep.get('id')}'"]
    if media_name == "video":
        res = f"{rep.get('width', '?')}x{rep.get('height', '?')}"
        info_parts.append(f"Resolution={res}")
        if rep.get("frameRate"):
            info_parts.append(f"FrameRate='{rep.get('frameRate')}'")
    elif media_name == "audio":
        if rep.get("audioSamplingRate"):
            info_parts.append(f"SamplingRate='{rep.get('audioSamplingRate')}'")

    info_parts.append(f"Bandwidth={utils.format_bandwidth(rep.get('bandwidth'))}")
    info_parts.append(f"Codecs='{rep.get('codecs')}'")
    return ", ".join(info_parts)


async def fetch_and_parse_mpd(
    session: aiohttp.ClientSession, mpd_url: str, retries: int, retry_delay: float
) -> tuple[etree._Element | None, bool]:
    is_ended = False
    try:
        xml_content, headers = await io.fetch_url_content(session, mpd_url, retries, retry_delay, log.MPD)

        if headers and "x-fb-video-broadcast-ended" in headers:
            is_ended = True

        if not xml_content:
            return None, is_ended

        return etree.fromstring(xml_content), is_ended

    except (etree.XMLSyntaxError, Exception):
        log.MPD.exception("Failed to parse MPD XML. This may happen normally at the end of a stream.")
        return None, is_ended


def parse_initial_stream_info(
    root: etree._Element, preferred_video_ids: list[str] | None, preferred_audio_ids: list[str] | None
) -> dict[str, Any]:
    video_rep = select_representation(root, "video/mp4", preferred_video_ids)
    audio_rep = select_representation(root, "audio/mp4", preferred_audio_ids)

    video_template = video_rep.find("mpd:SegmentTemplate", namespaces=NS)
    audio_template = audio_rep.find("mpd:SegmentTemplate", namespaces=NS)

    publish_frame_time_str = root.get("publishFrameTime")
    publish_frame_time = int(publish_frame_time_str) if publish_frame_time_str else None

    last_segment = video_template.find(".//mpd:S[last()]", namespaces=NS)
    if last_segment is None:
        raise ValueError("Could not find any segments in the MPD.")

    return {
        "video": {"init": video_template.get("initialization"), "media": video_template.get("media")},
        "audio": {"init": audio_template.get("initialization"), "media": audio_template.get("media")},
        "publish_frame_time": publish_frame_time,
        "initial_t": int(last_segment.get("t", 0)),
    }


def select_representation(root: etree._Element, media_type: str, preferred_ids: list[str] | None) -> etree._Element:
    media_name = media_type.split("/")[0]  # "video" or "audio"

    xpath_query = f'//mpd:Representation[@mimeType="{media_type}"]'
    all_reps = root.xpath(xpath_query, namespaces=NS)
    if not all_reps:
        raise ValueError(f"No representations found for mimeType '{media_type}'")

    if preferred_ids:
        for rep_id in preferred_ids:
            for rep in all_reps:
                if rep.get("id") == rep_id:
                    log.INIT.info(
                        f"Found user-specified {media_name} representation: {_format_rep_info(rep, media_name)}"
                    )
                    return rep
        log.INIT.warning(
            f"None of the preferred {media_name} IDs found: {preferred_ids}. Falling back to highest bitrate."
        )

    log.INIT.debug(f"Selecting best {media_name} representation by highest bitrate.")
    best_rep = max(all_reps, key=lambda r: int(r.get("bandwidth", 0)))
    log.INIT.info(f"Selected {media_name} representation: {_format_rep_info(best_rep, media_name)}")
    return best_rep
