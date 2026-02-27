"""CLI Memory v1.5 wrappers.

This package provides thin, locked wrappers around the existing
`tracks.cli_sqlite` runners so experiments can be reproduced with a
stable v1.5 configuration surface.
"""

from .profile import V15_LOCKED, V15Policy

__all__ = ["V15_LOCKED", "V15Policy"]
