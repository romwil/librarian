"""Uvicorn entry point."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from librarian.config import load_dotenv
from librarian.web.logging_config import configure_logging


def main() -> None:
    load_dotenv()
    configure_logging()
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8793"))
    data_dir = Path(os.environ.get("DATA_DIR", "./config"))
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DATA_DIR", str(data_dir))
    uvicorn.run(
        "librarian.web.app:app",
        host=host,
        port=port,
        reload=False,
        workers=1,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
