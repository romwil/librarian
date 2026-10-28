"""The LLM identify step: evidence for the model, merge, then folder hygiene after it."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from librarian.identify.inspect import (
    _unexpected_extra_files,
    expand_organize_payload,
    is_mixed_comic_ebook_payload,
)
from librarian.kinds import KIND_AUDIOBOOK, KIND_BOOK, KIND_COMIC, KIND_MAGAZINE, KIND_MUSIC
from librarian.naming.identity import Identity
from librarian.naming.tokens import looks_like_dump_title
from librarian.review_reasons import (
    REVIEW_COMICVINE_AMBIGUOUS,
    REVIEW_COMICVINE_UNMATCHED,
    REVIEW_CONVERT,
    REVIEW_EXTRA,
)


def identify_evidence(
    folder: Path,
    indexer_item: Optional[Dict[str, Any]],
    files: Sequence[Path],
    identity: Identity,
) -> str:
    item = indexer_item or {}
    sought = item.get("sought") if isinstance(item.get("sought"), dict) else {}
    names = ", ".join(path.name for path in files)
    return (
        f"folder: {folder.name}\n"
        f"files: {names}\n"
        f"sought_kind: {sought.get('kind') or item.get('kind') or ''}\n"
        f"sought_title: {sought.get('title') or item.get('title') or ''}\n"
        f"sought_author: {sought.get('author') or item.get('author') or ''}\n"
        f"sought_isbn: {sought.get('isbn') or item.get('isbn') or ''}\n"
        f"indexer_title: {item.get('title') or ''}\n"
        f"indexer_author: {item.get('author') or ''}\n"
        f"indexer_isbn: {item.get('isbn') or ''}\n"
        f"parsed_title: {identity.title}\n"
        f"parsed_author: {identity.author}\n"
        f"parsed_kind: {identity.kind}\n"
        f"parsed_isbn: {identity.isbn}\n"
        f"parsed_series: {identity.series_name} {identity.series_index}\n"
    )


def _apply_post_llm_review(identity: Identity, folder: Path) -> List[Path]:
    """Folder hygiene after a successful LLM identity. Keep true multi-work extras in Review."""
    files = expand_organize_payload(folder)
    if is_mixed_comic_ebook_payload(files):
        identity.review_reason = REVIEW_EXTRA
        identity.confidence = "low"
        return files
    extra = _unexpected_extra_files(files)
    if extra and identity.kind not in (KIND_MUSIC, KIND_AUDIOBOOK, KIND_MAGAZINE):
        identity.review_reason = REVIEW_EXTRA
        identity.confidence = "low"
    if identity.kind == KIND_BOOK:
        suffixes = {path.suffix.lower() for path in files}
        if suffixes == {".pdf"}:
            identity.review_reason = identity.review_reason or REVIEW_CONVERT
            identity.confidence = "low"
        elif (
            identity.isbn
            and identity.author
            and identity.title
            and identity.confidence == "high"
            and identity.review_reason != REVIEW_EXTRA
        ):
            identity.review_reason = None
    if identity.kind in (KIND_COMIC, KIND_MAGAZINE) and identity.series_name and identity.series_index:
        suffixes = {path.suffix.lower() for path in files}
        # Final shelf is CBZ only — CBR and PDF comics must remux before auto-organize.
        if identity.kind == KIND_COMIC:
            has_cbz = ".cbz" in suffixes
            needs_cbz = (".cbr" in suffixes or ".pdf" in suffixes) and not has_cbz
            if needs_cbz:
                identity.review_reason = identity.review_reason or REVIEW_CONVERT
                identity.confidence = "low"
            elif identity.confidence == "high" and identity.review_reason not in (
                REVIEW_EXTRA,
                REVIEW_COMICVINE_AMBIGUOUS,
                REVIEW_COMICVINE_UNMATCHED,
            ):
                identity.review_reason = None
        elif identity.confidence == "high" and identity.review_reason != REVIEW_EXTRA:
            identity.review_reason = None
    return files



def needs_llm(identity: Identity) -> bool:
    """Low confidence, a dump-looking title, or a book/audiobook with no author."""
    needs_author = identity.kind in (KIND_BOOK, KIND_AUDIOBOOK) and not identity.author
    return identity.confidence != "high" or looks_like_dump_title(identity.title) or needs_author


def apply_llm_identity(
    identity: Identity,
    folder: Path,
    *,
    indexer_item: Optional[Dict[str, Any]],
    files: List[Path],
    llm_client: Any,
) -> Tuple[Identity, List[Path]]:
    """Ask the model when the stack is unsure. A failed call keeps the stack identity."""
    if llm_client is None or not needs_llm(identity):
        return identity, files
    evidence = identify_evidence(folder, indexer_item, files, identity)
    try:
        from librarian.llm import merge_llm_identity

        parsed = llm_client.identify(evidence)
        identity = merge_llm_identity(identity, parsed, evidence)
    except Exception:
        return identity, files
    return identity, _apply_post_llm_review(identity, folder)
