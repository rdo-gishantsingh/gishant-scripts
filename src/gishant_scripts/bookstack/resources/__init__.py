"""BookStack API resource modules."""

from gishant_scripts.bookstack.resources.attachments import AttachmentsResource
from gishant_scripts.bookstack.resources.audit_log import AuditLogResource
from gishant_scripts.bookstack.resources.books import BooksResource
from gishant_scripts.bookstack.resources.chapters import ChaptersResource
from gishant_scripts.bookstack.resources.comments import CommentsResource
from gishant_scripts.bookstack.resources.content_permissions import ContentPermissionsResource
from gishant_scripts.bookstack.resources.image_gallery import ImageGalleryResource
from gishant_scripts.bookstack.resources.pages import PagesResource
from gishant_scripts.bookstack.resources.recycle_bin import RecycleBinResource
from gishant_scripts.bookstack.resources.roles import RolesResource
from gishant_scripts.bookstack.resources.search import SearchResource
from gishant_scripts.bookstack.resources.shelves import ShelvesResource
from gishant_scripts.bookstack.resources.system import SystemResource
from gishant_scripts.bookstack.resources.users import UsersResource

__all__ = [
    "AttachmentsResource",
    "AuditLogResource",
    "BooksResource",
    "ChaptersResource",
    "CommentsResource",
    "ContentPermissionsResource",
    "ImageGalleryResource",
    "PagesResource",
    "RecycleBinResource",
    "RolesResource",
    "SearchResource",
    "ShelvesResource",
    "SystemResource",
    "UsersResource",
]
