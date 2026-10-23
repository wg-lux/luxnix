"""Restrictive file helpers for generated passwords and keys."""

from lx_administration.permissions import PRIVATE_FILE_MODE as PRIVATE_FILE_MODE
from lx_administration.permissions import write_private_text as write_private_text

__all__ = ["PRIVATE_FILE_MODE", "write_private_text"]
