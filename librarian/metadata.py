"""OPF and ComicInfo writers. Never invent a blurb."""

from __future__ import annotations

import xml.sax.saxutils as sax
from pathlib import Path
from typing import Any, Mapping


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
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uuid_id" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>{_esc(identity.get("title"))}</dc:title>
    <dc:creator opf:role="aut">{_esc(identity.get("author"))}</dc:creator>
    <dc:identifier id="uuid_id">{_esc(uid)}</dc:identifier>
    <dc:language>en</dc:language>
    <dc:publisher>{_esc(identity.get("publisher"))}</dc:publisher>
    <dc:date>{_esc(published)}</dc:date>
    <dc:subject>{_esc(identity.get("genre"))}</dc:subject>
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


def write_comicinfo(folder: Path, identity: Mapping[str, Any], *, guid: str = "", page_count: int = 0) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
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
    path = folder / "ComicInfo.xml"
    path.write_text(xml, encoding="utf-8")
    return path
