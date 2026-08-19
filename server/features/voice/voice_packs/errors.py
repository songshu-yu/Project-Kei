"""Stable, path-safe errors for Voice Pack lifecycle operations."""

from __future__ import annotations


class VoicePackError(Exception):
    code = "voice_pack_error"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class VoicePackManifestError(VoicePackError):
    code = "voice_pack_manifest_invalid"


class VoicePackPackageError(VoicePackError):
    code = "voice_pack_package_invalid"


class VoicePackRegistryError(VoicePackError):
    code = "voice_pack_registry_error"


class VoicePackConflictError(VoicePackError):
    code = "voice_pack_conflict"


class VoicePackNotFoundError(VoicePackError):
    code = "voice_pack_not_found"


class VoicePackSwitchError(VoicePackError):
    code = "voice_pack_switch_failed"
