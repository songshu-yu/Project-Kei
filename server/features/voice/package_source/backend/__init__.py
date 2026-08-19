"""PK-210 installable voice package entrypoint."""

from .module import register, unregister

__all__ = ["register", "unregister"]
