"""BookStack API wrapper for managing documentation.

This module provides a comprehensive wrapper for the BookStack REST API,
enabling programmatic management of pages, chapters, books, shelves,
attachments, and other BookStack resources.
"""

from gishant_scripts.bookstack.client import BookStackClient

__all__ = ["BookStackClient"]
