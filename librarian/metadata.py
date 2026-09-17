"""OPF and ComicInfo writers and readers. Never invent a blurb."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import xml.sax.saxutils as sax
import zipfile
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from librarian.identify import extract_isbn


def _esc(value: object) -> str:
    return sax.escape(str(value or "").strip())


def write_opf(folder: Path, identity: Mapping[str, Any], *, guid: str = "") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    isbn = str(identity.get("isbn") or "").strip()
    uid = isbn or guid or identity.get("title") or "unknown"
    series = str(identity.get("series_name") or "").strip()
    index = str(identity.get("series_index") or "").strip()
    year = identity.get("year")
    published = f"{year}-01-01" if year else ""
    subjects = _subjects_from_genre(identity.get("genre"))
    subject_xml = "\n".join(f"    <dc:subject>{_esc(item)}</dc:subject>" for item in subjects)
    if not subject_xml:
        subject_xml = "    <dc:subject></dc:subject>"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uuid_id" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>{_esc(identity.get("title"))}</dc:title>
    <dc:creator opf:role="aut">{_esc(identity.get("author"))}</dc:creator>
    <dc:identifier id="uuid_id">{_esc(uid)}</dc:identifier>
    <dc:language>en</dc:language>
    <dc:publisher>{_esc(identity.get("publisher"))}</dc:publisher>
    <dc:date>{_esc(published)}</dc:date>
{subject_xml}
    <dc:description>{_esc(identity.get("description"))}</dc:description>
    <meta name="calibre:series" content="{_esc(series)}"/>
    <meta name="calibre:series_index" content="{_esc(index)}"/>
    <dc:source>{_esc(guid)}</dc:source>
  </metadata>
</package>
"""
    path = folder / "metadata.opf"
    path.write_text(xml, encoding="utf-8")
    return path


def _subjects_from_genre(value: object) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"[,;/|]+", text) if part.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        key = part.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(part)
    return out


def comicinfo_xml(identity: Mapping[str, Any], *, guid: str = "", page_count: int = 0) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ComicInfo>
  <Series>{_esc(identity.get("series_name") or identity.get("title"))}</Series>
  <Number>{_esc(identity.get("series_index"))}</Number>
  <Title>{_esc(identity.get("title"))}</Title>
  <Year>{_esc(identity.get("year") or "")}</Year>
  <Writer>{_esc(identity.get("author"))}</Writer>
  <Publisher>{_esc(identity.get("publisher"))}</Publisher>
  <PageCount>{int(page_count or 0)}</PageCount>
  <Notes>indexer guid: {_esc(guid)}</Notes>
</ComicInfo>
"""


def write_comicinfo(folder: Path, identity: Mapping[str, Any], *, guid: str = "", page_count: int = 0) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "ComicInfo.xml"
    path.write_text(comicinfo_xml(identity, guid=guid, page_count=page_count), encoding="utf-8")
    return path


_YEAR = re.compile(r"(19\d{2}|20\d{2})")
_CONTAINER_PATH = re.compile(r'full-path="([^"]+)"', re.IGNORECASE)


def _text(el: Optional[ET.Element]) -> str:
    if el is None or el.text is None:
        return ""
    return str(el.text).strip()


def _first_child(root: ET.Element, *tags: str) -> Optional[ET.Element]:
    lowered = {tag.lower() for tag in tags}
    for child in root.iter():
        local = child.tag.rsplit("}", 1)[-1]
        if local.lower() in lowered:
            return child
    return None


def parse_opf_bytes(data: bytes) -> Dict[str, Any]:
    """Parse an OPF package into identity fields. Empty dict if unreadable."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return {}
    title = _text(_first_child(root, "title"))
    author = _text(_first_child(root, "creator"))
    isbn = ""
    for child in root.iter():
        local = child.tag.rsplit("}", 1)[-1]
        if local.lower() != "identifier":
            continue
        found = extract_isbn(_text(child) or "")
        if found:
            isbn = found
            break
    year = None
    date = _text(_first_child(root, "date"))
    match = _YEAR.search(date)
    if match:
        year = int(match.group(1))
    series_name = ""
    series_index = ""
    for child in root.iter():
        local = child.tag.rsplit("}", 1)[-1]
        if local.lower() != "meta":
            continue
        name = (child.attrib.get("name") or "").lower()
        content = child.attrib.get("content") or _text(child)
        if name == "calibre:series":
            series_name = content.strip()
        elif name == "calibre:series_index":
            series_index = content.strip()
    out: Dict[str, Any] = {}
    if title:
        out["title"] = title
    if author:
        out["author"] = author
    if isbn:
        out["isbn"] = isbn
    if year:
        out["year"] = year
    if series_name:
        out["series_name"] = series_name
    if series_index:
        out["series_index"] = series_index
    publisher = _text(_first_child(root, "publisher"))
    if publisher:
        out["publisher"] = publisher
    description = _text(_first_child(root, "description"))
    if description:
        out["description"] = description
    subjects: list[str] = []
    for child in root.iter():
        local = child.tag.rsplit("}", 1)[-1]
        if local.lower() != "subject":
            continue
        text = _text(child)
        if text:
            subjects.append(text)
    genre = join_subjects(subjects)
    if genre:
        out["genre"] = genre
    return out


def join_subjects(values: object, *, limit: int = 12) -> str:
    """Normalize subject/genre lists into a single catalog genre string."""
    items: list[str] = []
    if isinstance(values, str):
        items = _subjects_from_genre(values)
    elif isinstance(values, (list, tuple)):
        for raw in values:
            if isinstance(raw, Mapping):
                text = str(raw.get("tag") or raw.get("name") or raw.get("subject") or "").strip()
            else:
                text = str(raw or "").strip()
            if text:
                items.extend(_subjects_from_genre(text))
    return ", ".join(items[: max(1, int(limit))]) if items else ""


def read_opf(path: Path) -> Dict[str, Any]:
    file_path = Path(path)
    if not file_path.is_file():
        return {}
    try:
        return parse_opf_bytes(file_path.read_bytes())
    except OSError:
        return {}


def parse_comicinfo_bytes(data: bytes) -> Dict[str, Any]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return {}
    series = _text(_first_child(root, "Series"))
    number = _text(_first_child(root, "Number"))
    title = _text(_first_child(root, "Title"))
    writer = _text(_first_child(root, "Writer"))
    year_text = _text(_first_child(root, "Year"))
    year = None
    if year_text.isdigit():
        year = int(year_text)
    out: Dict[str, Any] = {}
    if series:
        out["series_name"] = series
    if number:
        out["series_index"] = number
    if title:
        out["title"] = title
    elif series and number:
        out["title"] = f"{series} #{number}"
    if writer:
        out["author"] = writer
    if year:
        out["year"] = year
    publisher = _text(_first_child(root, "Publisher"))
    if publisher:
        out["publisher"] = publisher
    return out


def read_comicinfo(path: Path) -> Dict[str, Any]:
    file_path = Path(path)
    if not file_path.is_file():
        return {}
    try:
        return parse_comicinfo_bytes(file_path.read_bytes())
    except OSError:
        return {}


def sidecar_named(folder: Path, *names: str) -> Optional[Path]:
    """Find a sidecar by name, case-insensitive (Linux roots are case-sensitive)."""
    directory = Path(folder)
    if not directory.is_dir():
        return None
    wanted = {name.lower() for name in names}
    for name in names:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    try:
        for path in directory.iterdir():
            if path.is_file() and path.name.lower() in wanted:
                return path
    except OSError:
        return None
    return None


def read_folder_metadata(folder: Path) -> Dict[str, Any]:
    """Merge sidecar OPF then ComicInfo. ComicInfo wins on overlapping keys."""
    merged: Dict[str, Any] = {}
    opf = sidecar_named(folder, "metadata.opf")
    if opf is not None:
        merged.update(read_opf(opf))
    comic = sidecar_named(folder, "ComicInfo.xml", "comicinfo.xml")
    if comic is not None:
        merged.update(read_comicinfo(comic))
    return merged


def read_epub_opf(epub: Path) -> Dict[str, Any]:
    archive = Path(epub)
    if not archive.is_file():
        return {}
    try:
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            by_lower = {name.lower(): name for name in names}
            opf_name = ""
            container = by_lower.get("meta-inf/container.xml")
            if container:
                match = _CONTAINER_PATH.search(zf.read(container).decode("utf-8", errors="replace"))
                if match:
                    opf_name = match.group(1)
            if not opf_name:
                for name in names:
                    if name.lower().endswith(".opf"):
                        opf_name = name
                        break
            if not opf_name:
                return {}
            return parse_opf_bytes(zf.read(opf_name))
    except (OSError, zipfile.BadZipFile, KeyError):
        return {}


def read_cbz_comicinfo(cbz: Path) -> Dict[str, Any]:
    archive = Path(cbz)
    if not archive.is_file():
        return {}
    try:
        with zipfile.ZipFile(archive) as zf:
            for name in zf.namelist():
                if Path(name).name.lower() == "comicinfo.xml":
                    return parse_comicinfo_bytes(zf.read(name))
    except (OSError, zipfile.BadZipFile, KeyError):
        return {}
    return {}


def read_flac_tags(path: Path) -> Dict[str, Any]:
    """Vorbis comments from a FLAC stream. Layout still wins if tags are missing."""
    tags = read_audio_tags(path)
    out: Dict[str, Any] = {}
    if tags.get("author"):
        out["author"] = tags["author"]
    album = str(tags.get("album") or tags.get("series_name") or "")
    if album:
        out["title"] = album
        out["series_name"] = album
    elif tags.get("track_title"):
        out["title"] = str(tags["track_title"])
    elif tags.get("title"):
        out["title"] = str(tags["title"])
    if tags.get("year"):
        out["year"] = tags["year"]
    return out


def read_audio_tags(path: Path) -> Dict[str, Any]:
    """Album/artist/track tags. FLAC is parsed in-process; mutagen covers other formats."""
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix == ".flac":
        comments = _read_flac_comments(file_path)
        mapped = _identity_from_audio_comments(comments)
        if mapped:
            return mapped
    if suffix in {".flac", ".mp3", ".m4a", ".m4b", ".ogg", ".opus", ".mp4", ".aac"}:
        mapped = _identity_from_audio_comments(_mutagen_comments(file_path))
        if mapped:
            return mapped
    return {}


def read_pdf_info(path: Path) -> Dict[str, Any]:
    """Cheap PDF Info dict (Title/Author/Year). Empty if the trailer is unreadable."""
    file_path = Path(path)
    if file_path.suffix.lower() != ".pdf" or not file_path.is_file():
        return {}
    try:
        data = file_path.read_bytes()[:65536]
    except OSError:
        return {}
    info_idx = data.find(b"/Info")
    blob = data[info_idx : info_idx + 4096] if info_idx >= 0 else data
    title = _pdf_info_string(blob, b"/Title")
    author = _pdf_info_string(blob, b"/Author")
    date = _pdf_info_string(blob, b"/CreationDate") or _pdf_info_string(blob, b"/ModDate")
    out: Dict[str, Any] = {}
    if title:
        out["title"] = title
    if author:
        out["author"] = author
    match = _YEAR.search(date)
    if match:
        out["year"] = int(match.group(1))
    return out


def _read_flac_comments(file_path: Path) -> Dict[str, str]:
    try:
        with file_path.open("rb") as handle:
            if handle.read(4) != b"fLaC":
                return {}
            while True:
                header = handle.read(4)
                if len(header) < 4:
                    break
                is_last = header[0] & 0x80
                block_type = header[0] & 0x7F
                length = int.from_bytes(header[1:4], "big")
                payload = handle.read(length)
                if len(payload) < length:
                    break
                if block_type == 4:
                    return _parse_vorbis_comment(payload)
                if is_last:
                    break
    except OSError:
        return {}
    return {}


def _mutagen_comments(path: Path) -> Dict[str, str]:
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return {}
    try:
        audio = MutagenFile(path)
    except Exception:
        return {}
    if audio is None:
        return {}
    comments: Dict[str, str] = {}
    tags = getattr(audio, "tags", None)
    if not tags:
        return {}
    for key in tags.keys():
        try:
            value = tags[key]
        except Exception:
            continue
        text = _mutagen_value(value)
        if not text:
            continue
        comments[str(key).split(":")[-1].strip().lower()] = text
        comments[str(key).strip().lower()] = text
    # MP4 four-letter keys
    for raw_key, aliases in (
        ("\xa9nam", "title"),
        ("\xa9alb", "album"),
        ("\xa9ART", "artist"),
        ("aART", "albumartist"),
        ("\xa9day", "date"),
        ("\xa9gen", "genre"),
        ("trkn", "tracknumber"),
        ("disk", "discnumber"),
        ("\xa9wrt", "artist"),
        ("stik", "stik"),
    ):
        if raw_key in tags and aliases not in comments:
            text = _mutagen_value(tags[raw_key])
            if text:
                comments[aliases] = text
    return comments


def _mutagen_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    if isinstance(value, (list, tuple)):
        if not value:
            return ""
        first = value[0]
        if isinstance(first, (list, tuple)) and first:
            return str(first[0]).strip()
        return _mutagen_value(first)
    text = str(value).strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    return text


def _identity_from_audio_comments(comments: Mapping[str, str]) -> Dict[str, Any]:
    if not comments:
        return {}
    lowered = {str(key).lower(): str(value).strip() for key, value in comments.items() if str(value).strip()}
    artist = (
        lowered.get("albumartist")
        or lowered.get("album artist")
        or lowered.get("aart")
        or lowered.get("artist")
        or lowered.get("©art")
        or ""
    )
    album = lowered.get("album") or lowered.get("©alb") or ""
    title = lowered.get("title") or lowered.get("©nam") or ""
    date = lowered.get("date") or lowered.get("year") or lowered.get("©day") or ""
    tracknumber = _first_number(lowered.get("tracknumber") or lowered.get("track") or lowered.get("trkn") or "")
    discnumber = _first_number(lowered.get("discnumber") or lowered.get("disc") or lowered.get("disk") or "")
    mbid = (
        lowered.get("musicbrainz_albumid")
        or lowered.get("musicbrainz album id")
        or lowered.get("musicbrainz_releasegroupid")
        or lowered.get("musicbrainz_trackid")
        or lowered.get("musicbrainz_recordingid")
        or ""
    )
    recording_mbid = lowered.get("musicbrainz_trackid") or lowered.get("musicbrainz_recordingid") or ""
    out: Dict[str, Any] = {}
    if artist:
        out["author"] = artist
    if album:
        out["album"] = album
        out["series_name"] = album
        out["title"] = album
    elif title:
        out["title"] = title
    if title:
        out["track_title"] = title
    if tracknumber:
        out["tracknumber"] = tracknumber
    if discnumber:
        out["discnumber"] = discnumber
    match = _YEAR.search(date)
    if match:
        out["year"] = int(match.group(1))
    if mbid:
        out["mbid"] = mbid
    if recording_mbid:
        out["recording_mbid"] = recording_mbid
    genre = lowered.get("genre") or lowered.get("©gen") or ""
    if genre:
        out["genre"] = genre
    if _comments_look_like_audiobook(lowered):
        out["kind"] = "audiobook"
    return out


def _comments_look_like_audiobook(comments: Mapping[str, str]) -> bool:
    blob = " ".join(
        str(comments.get(key) or "").lower()
        for key in ("media", "mediatype", "itunesmediatype", "genre", "©gen", "stik", "compilation")
    )
    if "audiobook" in blob or "spoken" in blob:
        return True
    stik = str(comments.get("stik") or "").strip()
    return stik in {"2", "Audiobook"}


def _first_number(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.match(r"(\d+)", text.split("/")[0].strip())
    return str(int(match.group(1))) if match else ""


def _pdf_info_string(blob: bytes, key: bytes) -> str:
    idx = blob.find(key)
    if idx < 0:
        return ""
    rest = blob[idx + len(key) :].lstrip()
    if rest.startswith(b"("):
        raw = bytearray()
        i = 1
        while i < len(rest):
            ch = rest[i]
            if ch == 0x5C and i + 1 < len(rest):  # backslash
                raw.append(rest[i + 1])
                i += 2
                continue
            if ch == 0x29:  # )
                break
            raw.append(ch)
            i += 1
        text = bytes(raw)
        if text.startswith(b"\xfe\xff") or text.startswith(b"\xff\xfe"):
            return text.decode("utf-16", errors="replace").strip()
        return text.decode("latin-1", errors="replace").strip()
    if rest.startswith(b"<"):
        end = rest.find(b">")
        if end > 1:
            try:
                hexed = bytes.fromhex(rest[1:end].decode("ascii", errors="ignore").replace(" ", ""))
            except ValueError:
                return ""
            if hexed.startswith(b"\xfe\xff") or hexed.startswith(b"\xff\xfe"):
                return hexed.decode("utf-16", errors="replace").strip()
            return hexed.decode("latin-1", errors="replace").strip()
    return ""


def _parse_vorbis_comment(payload: bytes) -> Dict[str, str]:
    if len(payload) < 8:
        return {}
    vendor_len = int.from_bytes(payload[0:4], "little")
    cursor = 4 + vendor_len
    if cursor + 4 > len(payload):
        return {}
    count = int.from_bytes(payload[cursor : cursor + 4], "little")
    cursor += 4
    comments: Dict[str, str] = {}
    for _ in range(count):
        if cursor + 4 > len(payload):
            break
        size = int.from_bytes(payload[cursor : cursor + 4], "little")
        cursor += 4
        if cursor + size > len(payload):
            break
        raw = payload[cursor : cursor + size].decode("utf-8", errors="replace")
        cursor += size
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        comments[key.strip().lower()] = value.strip()
    return comments


def extract_embedded_cover_bytes(path: Path) -> bytes:
    """Front-cover image bytes from embedded tags. Empty when absent or unreadable."""
    file_path = Path(path)
    if not file_path.is_file():
        return b""
    suffix = file_path.suffix.lower()
    if suffix == ".flac":
        data = _flac_picture_bytes(file_path)
        if data:
            return data
    return _mutagen_picture_bytes(file_path)


def _flac_picture_bytes(file_path: Path) -> bytes:
    try:
        with file_path.open("rb") as handle:
            if handle.read(4) != b"fLaC":
                return b""
            while True:
                header = handle.read(4)
                if len(header) < 4:
                    break
                is_last = header[0] & 0x80
                block_type = header[0] & 0x7F
                length = int.from_bytes(header[1:4], "big")
                payload = handle.read(length)
                if len(payload) < length:
                    break
                if block_type == 6:
                    picture = _decode_flac_picture(payload)
                    if picture:
                        return picture
                if is_last:
                    break
    except OSError:
        return b""
    return b""


def _decode_flac_picture(payload: bytes) -> bytes:
    if len(payload) < 32:
        return b""
    cursor = 4  # picture type
    mime_len = int.from_bytes(payload[cursor : cursor + 4], "big")
    cursor += 4
    if cursor + mime_len > len(payload):
        return b""
    cursor += mime_len
    desc_len = int.from_bytes(payload[cursor : cursor + 4], "big")
    cursor += 4
    if cursor + desc_len > len(payload):
        return b""
    cursor += desc_len
    cursor += 16  # width, height, depth, colors
    if cursor + 4 > len(payload):
        return b""
    data_len = int.from_bytes(payload[cursor : cursor + 4], "big")
    cursor += 4
    if data_len <= 0 or cursor + data_len > len(payload):
        return b""
    data = payload[cursor : cursor + data_len]
    from librarian.covers import looks_like_image

    return data if looks_like_image(data) else b""


def _mutagen_picture_bytes(path: Path) -> bytes:
    try:
        from mutagen import File as MutagenFile
        from mutagen.flac import FLAC
        from mutagen.id3 import ID3
        from mutagen.mp4 import MP4
    except ImportError:
        return b""
    try:
        audio = MutagenFile(path)
    except Exception:
        return b""
    if audio is None:
        return b""
    from librarian.covers import looks_like_image

    if isinstance(audio, FLAC) and getattr(audio, "pictures", None):
        for picture in audio.pictures:
            data = bytes(getattr(picture, "data", b"") or b"")
            if looks_like_image(data):
                return data
    tags = getattr(audio, "tags", None)
    if tags is None:
        return b""
    if isinstance(tags, ID3) or hasattr(tags, "getall"):
        try:
            frames = tags.getall("APIC")  # type: ignore[attr-defined]
        except Exception:
            frames = []
        for frame in frames or []:
            data = bytes(getattr(frame, "data", b"") or b"")
            if looks_like_image(data):
                return data
    if isinstance(audio, MP4) or (isinstance(tags, dict) and "covr" in tags):
        covers = tags.get("covr") if isinstance(tags, dict) else None
        if covers:
            first = covers[0]
            data = bytes(first) if not isinstance(first, bytes) else first
            if looks_like_image(data):
                return data
    return b""


def write_audio_tags(path: Path, identity: Mapping[str, Any]) -> bool:
    """Write album/artist/track tags that already exist in identity. Never invents titles."""
    file_path = Path(path)
    if not file_path.is_file():
        return False
    artist = str(identity.get("author") or identity.get("albumartist") or "").strip()
    album = str(identity.get("album") or identity.get("series_name") or identity.get("title") or "").strip()
    title = str(identity.get("track_title") or "").strip()
    tracknumber = str(identity.get("tracknumber") or "").strip()
    discnumber = str(identity.get("discnumber") or "").strip()
    genre = str(identity.get("genre") or "").strip()
    if not any((artist, album, title, tracknumber, discnumber, genre)):
        return False
    if file_path.suffix.lower() == ".flac":
        return _write_flac_tags(
            file_path,
            artist=artist,
            album=album,
            title=title,
            tracknumber=tracknumber,
            discnumber=discnumber,
            genre=genre,
        )
    return _write_mutagen_tags(
        file_path,
        artist=artist,
        album=album,
        title=title,
        tracknumber=tracknumber,
        discnumber=discnumber,
        genre=genre,
    )


def _write_flac_tags(
    path: Path,
    *,
    artist: str,
    album: str,
    title: str,
    tracknumber: str,
    discnumber: str,
    genre: str,
) -> bool:
    """Replace Vorbis COMMENT block. Leaves picture/other blocks intact when possible."""
    try:
        from mutagen.flac import FLAC
    except ImportError:
        return False
    try:
        audio = FLAC(path)
    except Exception:
        return False
    if audio is None:
        return False
    if artist:
        audio["albumartist"] = [artist]
        audio["artist"] = [artist]
    if album:
        audio["album"] = [album]
    if title:
        audio["title"] = [title]
    if tracknumber:
        audio["tracknumber"] = [tracknumber]
    if discnumber:
        audio["discnumber"] = [discnumber]
    if genre:
        audio["genre"] = [genre]
    try:
        audio.save()
    except Exception:
        return False
    return True


def _write_mutagen_tags(
    path: Path,
    *,
    artist: str,
    album: str,
    title: str,
    tracknumber: str,
    discnumber: str,
    genre: str,
) -> bool:
    try:
        from mutagen import File as MutagenFile
        from mutagen.easyid3 import EasyID3
        from mutagen.id3 import ID3NoHeaderError
        from mutagen.mp4 import MP4
    except ImportError:
        return False
    suffix = path.suffix.lower()
    try:
        if suffix == ".mp3":
            try:
                tags = EasyID3(path)
            except ID3NoHeaderError:
                audio = MutagenFile(path, easy=True)
                if audio is None:
                    return False
                audio.add_tags()
                tags = audio
            if artist:
                tags["albumartist"] = artist
                tags["artist"] = artist
            if album:
                tags["album"] = album
            if title:
                tags["title"] = title
            if tracknumber:
                tags["tracknumber"] = tracknumber
            if discnumber:
                tags["discnumber"] = discnumber
            if genre:
                tags["genre"] = genre
            tags.save(path)
            return True
        audio = MutagenFile(path)
        if audio is None:
            return False
        if isinstance(audio, MP4) or path.suffix.lower() in {".m4a", ".m4b", ".mp4"}:
            if audio.tags is None:
                audio.add_tags()
            assert audio.tags is not None
            if artist:
                audio.tags["aART"] = [artist]
                audio.tags["\xa9ART"] = [artist]
            if album:
                audio.tags["\xa9alb"] = [album]
            if title:
                audio.tags["\xa9nam"] = [title]
            if tracknumber and tracknumber.isdigit():
                audio.tags["trkn"] = [(int(tracknumber), 0)]
            if discnumber and discnumber.isdigit():
                audio.tags["disk"] = [(int(discnumber), 0)]
            if genre:
                audio.tags["\xa9gen"] = [genre]
            audio.save()
            return True
        if audio.tags is None:
            try:
                audio.add_tags()
            except Exception:
                return False
        if artist:
            audio["albumartist"] = [artist]
            audio["artist"] = [artist]
        if album:
            audio["album"] = [album]
        if title:
            audio["title"] = [title]
        if tracknumber:
            audio["tracknumber"] = [tracknumber]
        if discnumber:
            audio["discnumber"] = [discnumber]
        if genre:
            audio["genre"] = [genre]
        audio.save()
        return True
    except Exception:
        return False


def apply_audio_tags_in_folder(
    folder: Path,
    identity: Mapping[str, Any],
    *,
    paths: Optional[Sequence[Path]] = None,
) -> int:
    """Optional tag write for audio files under a folder. Returns files updated."""
    directory = Path(folder)
    candidates = list(paths) if paths is not None else []
    if not candidates and directory.is_dir():
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix.lower() in {
                ".flac",
                ".mp3",
                ".m4a",
                ".m4b",
                ".ogg",
                ".opus",
                ".aac",
            }:
                candidates.append(path)
    written = 0
    for path in candidates:
        tags = read_audio_tags(path)
        merged = {
            "author": identity.get("author") or tags.get("author"),
            "album": identity.get("album") or identity.get("series_name") or tags.get("album"),
            "series_name": identity.get("series_name") or tags.get("series_name"),
            "track_title": tags.get("track_title") or identity.get("track_title"),
            "tracknumber": tags.get("tracknumber") or identity.get("tracknumber"),
            "discnumber": tags.get("discnumber") or identity.get("discnumber"),
            "genre": identity.get("genre") or tags.get("genre"),
        }
        # Never invent a track title — only write when we already have one from tags or identity.
        if not str(merged.get("track_title") or "").strip():
            continue
        if write_audio_tags(path, merged):
            written += 1
    return written

