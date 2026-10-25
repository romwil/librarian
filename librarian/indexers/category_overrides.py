"""Documented Newznab category trees for hosts whose caps omit categories.

DrunkenSlug's live ``t=caps`` response currently lists no categories. Discover
uses this published ``cat`` map (Books 7000, Audiobook 3030, and the rest of
the site's documented tree) so an empty capabilities list still has feeds to
walk. Ids and names only — API keys stay in settings, never here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from librarian.indexers.hosts import DRUNKENSLUG_ID, DRUNKENSLUG_URL
from librarian.nzbfinder import is_classic_newznab_host


def _tree(parent_id: int, name: str, leaves: Mapping[int, str]) -> Dict[str, Any]:
    return {
        "id": parent_id,
        "name": name,
        "subcategories": {str(cat_id): label for cat_id, label in leaves.items()},
    }


# Published DrunkenSlug category ids (standard Newznab numbering).
# Librarian walks the leaves ``category_feeds`` already understands: the
# Books family and Audiobook 3030 on the shelf, movies/TV/XXX only when
# Show categories is on. Console and PC stay in the tree for the record.
DRUNKENSLUG_CATEGORY_TREE: List[Dict[str, Any]] = [
    _tree(
        1000,
        "Console",
        {
            1010: "NDS",
            1020: "PSP",
            1030: "Wii",
            1040: "Xbox",
            1050: "Xbox 360",
            1060: "WiiWare/VC",
            1070: "XBOX 360 DLC",
            1080: "PS3",
            1110: "3DS",
            1130: "WiiU",
            1140: "Xbox One",
            1180: "PS4",
            1999: "Other",
        },
    ),
    _tree(
        2000,
        "Movies",
        {
            2010: "Foreign",
            2030: "SD",
            2040: "HD",
            2045: "UHD",
            2050: "3D",
            2060: "BluRay",
            2070: "DVD",
            2999: "Other",
        },
    ),
    _tree(
        3000,
        "Audio",
        {
            3010: "MP3",
            3020: "Video",
            3030: "Audiobook",
            3040: "Lossless",
            3060: "Foreign",
            3999: "Other",
        },
    ),
    _tree(
        4000,
        "PC",
        {
            4010: "0day",
            4020: "ISO",
            4030: "Mac",
            4050: "Games",
            4060: "Phone-IOS",
            4070: "Phone-Android",
            4999: "Phone-Other",
        },
    ),
    _tree(
        5000,
        "TV",
        {
            5020: "Foreign",
            5030: "SD",
            5040: "HD",
            5045: "UHD",
            5060: "Sport",
            5070: "Anime",
            5080: "Documentary",
            5999: "Other",
        },
    ),
    _tree(
        6000,
        "XXX",
        {
            6010: "DVD",
            6020: "WMV",
            6030: "XviD",
            6040: "HD",
            6045: "UHD",
            6050: "VR",
            6060: "Imageset",
            6070: "Packs",
            6080: "SD",
            6999: "Other",
        },
    ),
    _tree(
        7000,
        "Books",
        {
            7010: "Magazines",
            7020: "Ebook",
            7030: "Comics",
            7040: "Technical",
            7060: "Foreign",
            7999: "Other",
        },
    ),
    {"id": 0, "name": "Other", "subcategories": {}},
]

DRUNKENSLUG_CAPS: Dict[str, Any] = {
    "server": {"title": "DrunkenSlug", "url": DRUNKENSLUG_URL},
    "searching": {
        "search": {"available": "yes", "supported_params": "q,cat,limit,offset"},
    },
    "categories": DRUNKENSLUG_CATEGORY_TREE,
}


def documented_caps_for_host(host: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Caps stand-in when this host's live capabilities list no categories."""
    host_id = str(host.get("id") or "").strip()
    url = str(host.get("url") or "")
    if host_id == DRUNKENSLUG_ID or is_classic_newznab_host(url):
        return DRUNKENSLUG_CAPS
    return None
