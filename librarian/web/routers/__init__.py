"""FastAPI route modules registered from create_app."""

from librarian.web.routers.auth import register_auth_routes
from librarian.web.routers.hall import register_hall_routes
from librarian.web.routers.ingest import register_ingest_routes
from librarian.web.routers.maintain import register_maintain_routes
from librarian.web.routers.notifications import register_notification_routes
from librarian.web.routers.queue import register_queue_routes
from librarian.web.routers.reader_media import register_reader_media_routes
from librarian.web.routers.review import register_review_routes
from librarian.web.routers.search import register_search_routes
from librarian.web.routers.settings import register_settings_routes
from librarian.web.routers.works import register_works_routes

__all__ = [
    "register_auth_routes",
    "register_hall_routes",
    "register_ingest_routes",
    "register_maintain_routes",
    "register_notification_routes",
    "register_queue_routes",
    "register_reader_media_routes",
    "register_review_routes",
    "register_search_routes",
    "register_settings_routes",
    "register_works_routes",
]
