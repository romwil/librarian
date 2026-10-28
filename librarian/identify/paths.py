"""Storage paths (SAB container → readable host path) and library destination layout."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from librarian.kinds import KIND_AUDIOBOOK, KIND_BOOK, KIND_COMIC, KIND_MAGAZINE, KIND_MUSIC
from librarian.naming.extensions import STEM_EXTENSIONS
from librarian.naming.tokens import filename_stem, tidy_title, usenet_basename

COMPLETE_ROOT_FALLBACKS = ("/data/usenet/complete",)
HOST_DATA_PREFIX = "/mnt/user/data/"
CONTAINER_DATA_PREFIX = "/data/"
DOWNLOADS_PREFIXES = (
    "/downloads/complete/",
    "/downloads/downloads/",
    "/downloads/",
)


def usable_folder(folder: Optional[Union[Path, str]]) -> bool:
    """True when a path is a real location, not empty / cwd (Path(''))."""
    text = str(folder or "").strip()
    return bool(text) and text not in {".", str(Path())}


def _complete_roots(complete_root: str) -> List[Path]:
    text = str(complete_root or "").strip()
    if text:
        return [Path(text)]
    return [Path(raw) for raw in COMPLETE_ROOT_FALLBACKS if Path(raw).is_dir()]


def _unique_paths(paths: Sequence[Path]) -> List[Path]:
    seen: List[str] = []
    unique: List[Path] = []
    for path in paths:
        key = str(path)
        if not key or key == "." or key in seen:
            continue
        seen.append(key)
        unique.append(path)
    return unique


def _storage_relatives(storage: Path, complete_root: str = "") -> List[Path]:
    """Paths relative to SAB complete_dir, without doubling a /downloads prefix."""
    text = str(storage)
    relatives: List[Path] = []
    prefixes: List[str] = []
    root_text = str(complete_root or "").rstrip("/")
    if root_text:
        prefixes.append(root_text + "/")
        if root_text.startswith(CONTAINER_DATA_PREFIX):
            prefixes.append(HOST_DATA_PREFIX + root_text[len(CONTAINER_DATA_PREFIX) :] + "/")
        if root_text.startswith(HOST_DATA_PREFIX):
            prefixes.append(CONTAINER_DATA_PREFIX + root_text[len(HOST_DATA_PREFIX) :] + "/")
    prefixes.extend(
        (
            HOST_DATA_PREFIX + "usenet/complete/",
            CONTAINER_DATA_PREFIX + "usenet/complete/",
            *DOWNLOADS_PREFIXES,
        )
    )
    for prefix in prefixes:
        if text.startswith(prefix):
            rest = text[len(prefix) :]
            if rest:
                relatives.append(Path(rest))
    parts = storage.parts[1:] if storage.is_absolute() else storage.parts
    if parts:
        relatives.append(Path(*parts))
        if len(parts) > 1:
            relatives.append(Path(*parts[1:]))
    relatives.append(Path(storage.name))
    return _unique_paths(relatives)


def _guess_relative(storage: Path, relatives: Sequence[Path]) -> Path:
    """When nothing exists yet, do not invent /downloads/downloads/... under complete_root."""
    for relative in relatives:
        parts = relative.parts
        if parts and parts[0] == "downloads":
            continue
        if str(relative) not in {"", "."}:
            return Path(relative)
    return Path(storage.name)


def resolve_storage_path(storage: Path, complete_root: str = "") -> Path:
    """Map a SAB container path (often /downloads/...) onto a directory this process can read."""
    if not usable_folder(storage):
        return storage
    if storage.exists():
        return storage
    if str(storage).startswith(HOST_DATA_PREFIX):
        rewritten = Path(CONTAINER_DATA_PREFIX + str(storage)[len(HOST_DATA_PREFIX) :])
        if rewritten.exists():
            return rewritten
    roots = _complete_roots(complete_root)
    if not roots:
        return storage
    relatives = _storage_relatives(storage, complete_root)
    candidates: List[Path] = []
    for root_path in roots:
        candidates.append(root_path / storage.name)
        for relative in relatives:
            candidates.append(root_path / relative)
    ordered = _unique_paths(candidates)
    existing = [candidate for candidate in ordered if candidate.exists()]
    if existing:
        from librarian.identify.inspect import list_payload_files

        with_payload = [candidate for candidate in existing if list_payload_files(candidate)]
        return with_payload[0] if with_payload else existing[0]
    return roots[0] / _guess_relative(storage, relatives)


def path_layout_note(folder: Path) -> str:
    """Honest note when …/complete/downloads/… looks like a double prefix but is SAB’s category layout."""
    text = str(folder or "").replace("\\", "/")
    if "/complete/downloads/" in text or text.rstrip("/").endswith("/complete/downloads"):
        return (
            "The …/complete/downloads/… path is normal: SAB’s complete root ends at …/complete, "
            "and a downloads category adds that folder under it — not a doubled map."
        )
    return ""


def safe_path_part(value: str, fallback: str = "Unknown") -> str:
    text = tidy_title(value) or fallback
    text = re.sub(r"[/\\:]+", " - ", text).strip(" .")
    return text or fallback


def dest_layout(identity: Dict[str, Any], settings: Any, *, filename: str, source: Optional[Path] = None) -> Path:
    kind = identity.get("kind")
    title = safe_path_part(str(identity.get("title") or "Untitled"))
    author = safe_path_part(str(identity.get("author") or ""), fallback="Unknown Author")
    series = safe_path_part(str(identity.get("series_name") or title))
    index = safe_path_part(str(identity.get("series_index") or identity.get("year") or "000"), fallback="000")
    suffix = Path(filename).suffix.lower()

    if kind == KIND_BOOK:
        dest_name = f"{title}.epub" if suffix == ".epub" else Path(filename).name
        return Path(settings.books_root) / author / title / dest_name
    if kind == KIND_MAGAZINE:
        return Path(settings.magazines_root) / series / index / Path(filename).name
    if kind == KIND_COMIC:
        publisher = safe_path_part(str(identity.get("publisher") or ""), fallback="Unknown Publisher")
        volume_year = identity.get("volume_year")
        vol = str(int(volume_year)) if str(volume_year or "").isdigit() else ""
        series_folder = f"{series} ({vol})" if vol else series
        year = identity.get("year")
        year_bit = f" ({int(year)})" if str(year or "").isdigit() else ""
        fmt = str(identity.get("comic_format") or "").lower()
        subtitle = safe_path_part(str(identity.get("comic_subtitle") or ""))
        issue = str(identity.get("series_index") or index)
        if fmt in ("tpb", "omnibus", "compendium", "hc", "gn", "oneshot") or (
            not issue and subtitle
        ):
            label = subtitle or title
            if vol:
                dest_name = f"{series} - {label}{year_bit}.cbz"
            else:
                dest_name = f"{series} - {label}{year_bit}.cbz"
        else:
            if vol:
                dest_name = f"{series} v{vol} #{issue}{year_bit}.cbz"
            else:
                dest_name = f"{series} #{issue}{year_bit}.cbz"
        if suffix != ".cbz":
            dest_name = Path(filename).name
        return Path(settings.comics_root) / publisher / series_folder / dest_name
    if kind == KIND_AUDIOBOOK:
        year_val = identity.get("year")
        year_bit = f" ({year_val})" if year_val not in (None, "") else ""
        series = str(identity.get("series_name") or "").strip()
        index = str(identity.get("series_index") or "").strip()
        # Prefer canonical Title.m4b when shelving a remuxed book; otherwise keep source name.
        if suffix == ".m4b" or str(identity.get("asin") or "").strip():
            dest_name = f"{title}.m4b"
        else:
            dest_name = Path(filename).name
        root = Path(settings.audiobooks_root)
        if series:
            index_label = f"{index} - {title}{year_bit}" if index else f"{title}{year_bit}"
            return root / author / series / index_label / dest_name
        return root / author / f"{title}{year_bit}" / dest_name
    if kind == KIND_MUSIC:
        dest_name = _music_track_filename(identity, filename=filename, source=source)
        existing = existing_album_folder(identity, settings)
        if existing is not None:
            album_folder = existing
        else:
            album = safe_path_part(str(identity.get("series_name") or identity.get("album") or title))
            album_folder = Path(settings.incoming_music_root) / author / album
        disc = _music_discnumber(identity, source=source)
        if disc:
            album_folder = album_folder / f"Disc {disc}"
        return album_folder / dest_name
    raise ValueError(f"unsupported kind {kind}")


def existing_album_folder(identity: Mapping[str, Any], settings: Any) -> Optional[Path]:
    """Join an album that already exists under incoming_music_root or music_root."""
    artist = safe_path_part(str(identity.get("author") or ""), fallback="Unknown Author")
    album = safe_path_part(
        str(identity.get("series_name") or identity.get("album") or identity.get("title") or "")
    )
    if not album:
        return None
    for attr in ("incoming_music_root", "music_root"):
        root = Path(str(getattr(settings, attr, "") or "").strip())
        if not root:
            continue
        candidate = root / artist / album
        if candidate.is_dir():
            return candidate
        artist_dir = root / artist
        if artist_dir.is_dir():
            wanted = album.casefold()
            try:
                for child in artist_dir.iterdir():
                    if child.is_dir() and child.name.casefold() == wanted:
                        return child
            except OSError:
                continue
    return None


def music_state_for_folder(settings: Any, folder: Path) -> str:
    text = Path(folder)
    try:
        text.resolve().relative_to(Path(settings.music_root).resolve())
        return "promoted"
    except (ValueError, OSError):
        return "incoming"


def _safe_source_filename(filename: str) -> str:
    """Keep the source name; only strip separators and trailing dots (not Usenet tidy)."""
    name = usenet_basename(filename)
    stem = filename_stem(name).replace("/", "-").replace("\\", "-")
    stem = re.sub(r"[:]+", " - ", stem).strip(" .")
    suffix = ""
    lower = name.lower()
    for ext in sorted(STEM_EXTENSIONS, key=len, reverse=True):
        if lower.endswith(ext):
            suffix = name[len(name) - len(ext) :]
            break
    if not suffix and "." in name:
        maybe = name.rsplit(".", 1)[-1]
        if maybe.isalnum() and 1 <= len(maybe) <= 5:
            suffix = f".{maybe}"
    if not stem:
        return name or "track"
    return f"{stem}{suffix}"


def _music_track_filename(_identity: Mapping[str, Any], *, filename: str, source: Optional[Path]) -> str:
    """Original filename unless embedded track number + title tags exist (`NN - Title.ext`)."""
    # Folder/parse identity must not invent a dump-named track file.
    tags: Dict[str, Any] = {}
    if source is not None:
        try:
            from librarian.metadata import read_audio_tags

            tags = read_audio_tags(Path(source))
        except Exception:
            tags = {}
    track_title = str(tags.get("track_title") or "").strip()
    number = str(tags.get("tracknumber") or "").strip()
    if track_title and number.isdigit():
        name = safe_path_part(track_title)
        return f"{int(number):02d} - {name}{Path(filename).suffix}"
    return _safe_source_filename(filename)


def _music_discnumber(identity: Mapping[str, Any], *, source: Optional[Path]) -> str:
    """Disc folder segment when a trustworthy discnumber tag (or identity) is present."""
    raw = str(identity.get("discnumber") or "").strip()
    if not raw and source is not None:
        try:
            from librarian.metadata import read_audio_tags

            tags = read_audio_tags(Path(source))
            raw = str(tags.get("discnumber") or "").strip()
        except Exception:
            raw = ""
    if not raw or not raw.isdigit():
        return ""
    number = int(raw)
    return str(number) if number >= 1 else ""

