"""FastAPI route modules registered from create_app."""

from librarian.web.routers.auth import register_auth_routes
from librarian.web.routers.catalog import register_catalog_routes
from librarian.web.routers.ingest import register_ingest_routes
from librarian.web.routers.maintain import register_maintain_routes
from librarian.web.routers.review import register_review_routes
from librarian.web.routers.settings import register_settings_routes

__all__ = [
    "register_auth_routes",
    "register_catalog_routes",
    "register_ingest_routes",
    "register_maintain_routes",
    "register_review_routes",
    "register_settings_routes",
]
