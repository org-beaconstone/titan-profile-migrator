"""Deterministic verification of a regional copy against its source."""

from __future__ import annotations

import hashlib
import json

from .models import LegacyProfile, RegionalCopy, VerificationError


def profile_digest(profile: LegacyProfile) -> str:
    """Content digest of the fields a migration must preserve.

    Canonical JSON with sorted keys, so the digest is stable across runs,
    processes and machines. Two runs over unchanged source data always produce
    the same value, which is what makes a retry safe to compare against a copy
    written earlier.
    """
    canonical = json.dumps(
        {
            "customer_id": profile.customer_id,
            "tenant_id": profile.tenant_id,
            "email": profile.email,
            "display_name": profile.display_name,
            "updated_at": profile.updated_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Verifier:
    """Confirms a regional copy faithfully reproduces its source profile."""

    def verify(self, profile: LegacyProfile, copy: RegionalCopy) -> None:
        """Raises :class:`VerificationError` unless the copy matches.

        Nothing downstream may treat the source as deletable until this
        returns cleanly.
        """
        expected = profile_digest(profile)
        if copy.digest != expected:
            raise VerificationError(profile.customer_id, expected, copy.digest)
        if copy.customer_id != profile.customer_id or copy.tenant_id != profile.tenant_id:
            raise VerificationError(profile.customer_id, expected, copy.digest)
