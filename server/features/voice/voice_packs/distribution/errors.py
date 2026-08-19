"""Stable, path-redacted errors for Voice Pack distribution."""

from __future__ import annotations


class DistributionError(Exception):
    code = "voice_pack_distribution_failed"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code is not None:
            self.code = code
