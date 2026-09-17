"""Migration of a single profile out of the shared global store."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from .legacy_reader import LegacyReader
from .models import (
    LegacyProfile,
    MigrationAction,
    MigrationOutcome,
    MigrationError,
)
from .region_resolver import TenantRegionResolver
from .regional_writer import RegionalWriter
from .verifier import Verifier, profile_digest

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class BatchMigrator:
    """Writes one profile into its tenant's region and verifies the result.

    The source profile is only marked eligible for deletion after the regional
    copy has been verified, so an interrupted run never leaves a profile
    deletable without a good copy in place.
    """

    def __init__(
        self,
        reader: LegacyReader,
        resolver: TenantRegionResolver,
        writer: RegionalWriter,
        verifier: Verifier,
        clock: Clock = _utc_now,
    ) -> None:
        self._reader = reader
        self._resolver = resolver
        self._writer = writer
        self._verifier = verifier
        self._clock = clock

    def migrate(self, profile: LegacyProfile, *, dry_run: bool) -> MigrationOutcome:
        try:
            region = self._resolver.resolve(profile.tenant_id)
        except MigrationError as error:
            return self._skipped(profile, str(error))

        partition = self._writer.for_region(region)
        digest = profile_digest(profile)

        existing = partition.find(profile.customer_id)
        if existing is not None and existing.digest == digest:
            # A previous run already placed this profile. Verify what is there
            # and finish the bookkeeping rather than writing it a second time.
            self._verifier.verify(profile, existing)
            if not dry_run:
                self._reader.mark_eligible_for_deletion(profile.customer_id)
            return MigrationOutcome(
                customer_id=profile.customer_id,
                tenant_id=profile.tenant_id,
                region=region,
                action=MigrationAction.ALREADY_MIGRATED,
                reason="a verified regional copy is already in place",
                source_eligible_for_deletion=not dry_run,
            )

        if dry_run:
            return MigrationOutcome(
                customer_id=profile.customer_id,
                tenant_id=profile.tenant_id,
                region=region,
                action=MigrationAction.PLANNED,
                reason="would write a regional copy",
                source_eligible_for_deletion=False,
            )

        copy = partition.write(profile, digest, self._clock().isoformat())
        self._verifier.verify(profile, copy)
        self._reader.mark_eligible_for_deletion(profile.customer_id)

        return MigrationOutcome(
            customer_id=profile.customer_id,
            tenant_id=profile.tenant_id,
            region=region,
            action=MigrationAction.MIGRATED,
            reason="regional copy written and verified",
            source_eligible_for_deletion=True,
        )

    def _skipped(self, profile: LegacyProfile, reason: str) -> MigrationOutcome:
        return MigrationOutcome(
            customer_id=profile.customer_id,
            tenant_id=profile.tenant_id,
            region=None,
            action=MigrationAction.SKIPPED,
            reason=reason,
            source_eligible_for_deletion=False,
        )
