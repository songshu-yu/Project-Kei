"""Installable GitHub intelligence module entrypoint."""

from .provider import register

__all__ = ["register"]
