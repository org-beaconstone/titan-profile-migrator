"""Access to the shared global profile store that predates regional storage."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .models import LegacyProfile


class LegacyReader:
    """Reads profiles out of the shared global store.

    The migrator only ever reads here. A source profile is marked eligible for
    deletion once a regional copy has been written and verified, and the actual
    removal is a separate, later operation — so a failed migration can always
    be retried against untouched source data.
    """

    def __init__(self, profiles: Iterable[LegacyProfile]) -> None:
        self._profiles: dict[str, LegacyProfile] = {
            profile.customer_id: profile for profile in profiles
        }
        self._eligible_for_deletion: set[str] = set()

    def read_batch(self, limit: int) -> Sequence[LegacyProfile]:
        """Returns up to ``limit`` profiles still awaiting migration.

        Profiles already marked eligible for deletion are excluded, which is
        what makes a repeated run pick up where the last one stopped.
        """
        if limit <= 0:
            return []
        pending = [
            profile
            for customer_id, profile in sorted(self._profiles.items())
            if customer_id not in self._eligible_for_deletion
        ]
        return pending[:limit]

    def mark_eligible_for_deletion(self, customer_id: str) -> None:
        """Records that the source copy is safe to remove.

        Only call this after a regional copy has been verified.
        """
        if customer_id not in self._profiles:
            raise KeyError(f"No legacy profile for {customer_id}")
        self._eligible_for_deletion.add(customer_id)

    def eligible_for_deletion(self) -> frozenset[str]:
        """Customer ids whose source copy has been cleared for removal."""
        return frozenset(self._eligible_for_deletion)

    def remaining(self) -> int:
        """How many profiles are still awaiting migration."""
        return len(self._profiles) - len(self._eligible_for_deletion)
