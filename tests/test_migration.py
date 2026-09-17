"""Migration behaviour: regional placement, verification, retry, deletion."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from titan_profile_migrator import (
    BatchMigrator,
    HomeRegion,
    InMemoryPartitionWriter,
    LegacyProfile,
    LegacyReader,
    MigrationAction,
    MigrationPlanner,
    RegionalCopy,
    RegionalWriter,
    TenantRegionResolver,
    VerificationError,
    Verifier,
    profile_digest,
)

FIXED_NOW = datetime(2026, 4, 1, 10, 30, tzinfo=timezone.utc)

ASSIGNMENTS = {
    "tenant-eu-01": "EU",
    "tenant-us-01": "US",
    "tenant-apac-01": "APAC",
}


def profile(customer_id: str, tenant_id: str) -> LegacyProfile:
    return LegacyProfile(
        customer_id=customer_id,
        tenant_id=tenant_id,
        email="ada.lovelace@example.test",
        display_name="Ada Lovelace",
        updated_at="2026-03-02T09:00:00+00:00",
    )


class Harness:
    def __init__(self, *profiles: LegacyProfile) -> None:
        self.reader = LegacyReader(profiles)
        self.eu = InMemoryPartitionWriter(HomeRegion.EU)
        self.us = InMemoryPartitionWriter(HomeRegion.US)
        self.migrator = BatchMigrator(
            self.reader,
            TenantRegionResolver(ASSIGNMENTS),
            RegionalWriter([self.eu, self.us]),
            Verifier(),
            clock=lambda: FIXED_NOW,
        )
        self.planner = MigrationPlanner(self.reader, self.migrator)


def test_migrates_a_european_profile_into_the_european_estate() -> None:
    harness = Harness(profile("cust-1", "tenant-eu-01"))

    outcomes = harness.planner.plan(batch_size=10, dry_run=False)

    assert [outcome.action for outcome in outcomes] == [MigrationAction.MIGRATED]
    assert outcomes[0].region is HomeRegion.EU
    assert harness.eu.count() == 1
    assert harness.us.count() == 0


def test_migrates_a_united_states_profile_into_the_us_estate() -> None:
    harness = Harness(profile("cust-2", "tenant-us-01"))

    outcomes = harness.planner.plan(batch_size=10, dry_run=False)

    assert outcomes[0].region is HomeRegion.US
    assert harness.us.count() == 1
    assert harness.eu.count() == 0


def test_dry_run_reports_the_plan_without_writing_or_clearing_the_source() -> None:
    harness = Harness(profile("cust-3", "tenant-eu-01"))

    outcomes = harness.planner.plan(batch_size=10, dry_run=True)

    assert outcomes[0].action is MigrationAction.PLANNED
    assert outcomes[0].source_eligible_for_deletion is False
    assert harness.eu.count() == 0
    assert harness.reader.eligible_for_deletion() == frozenset()


def test_dry_run_is_repeatable_and_leaves_the_batch_unchanged() -> None:
    harness = Harness(profile("cust-4", "tenant-eu-01"))

    first = harness.planner.plan(batch_size=10, dry_run=True)
    second = harness.planner.plan(batch_size=10, dry_run=True)

    assert [o.action for o in first] == [o.action for o in second]
    assert harness.reader.remaining() == 1


def test_source_is_cleared_for_deletion_only_after_verification() -> None:
    harness = Harness(profile("cust-5", "tenant-eu-01"))

    outcomes = harness.planner.plan(batch_size=10, dry_run=False)

    assert outcomes[0].source_eligible_for_deletion is True
    assert harness.reader.eligible_for_deletion() == frozenset({"cust-5"})
    assert harness.reader.remaining() == 0


def test_failed_verification_leaves_the_source_intact() -> None:
    class WrongDigestPartition(InMemoryPartitionWriter):
        def write(
            self, profile: LegacyProfile, digest: str, written_at: str
        ) -> RegionalCopy:
            return super().write(profile, "0" * 64, written_at)

    reader = LegacyReader([profile("cust-6", "tenant-eu-01")])
    migrator = BatchMigrator(
        reader,
        TenantRegionResolver(ASSIGNMENTS),
        RegionalWriter([WrongDigestPartition(HomeRegion.EU)]),
        Verifier(),
        clock=lambda: FIXED_NOW,
    )

    with pytest.raises(VerificationError):
        migrator.migrate(profile("cust-6", "tenant-eu-01"), dry_run=False)

    assert reader.eligible_for_deletion() == frozenset()
    assert reader.remaining() == 1


def test_retry_after_a_completed_write_does_not_write_again() -> None:
    harness = Harness(profile("cust-7", "tenant-eu-01"))
    harness.planner.plan(batch_size=10, dry_run=False)

    # The source is cleared, so a fresh batch is empty and the run is a no-op.
    assert harness.planner.plan(batch_size=10, dry_run=False) == []

    # Re-offering the same profile finds the verified copy already in place.
    repeated = harness.migrator.migrate(profile("cust-7", "tenant-eu-01"), dry_run=False)
    assert repeated.action is MigrationAction.ALREADY_MIGRATED
    assert harness.eu.count() == 1


def test_profile_with_unsupported_region_is_skipped_and_not_written() -> None:
    harness = Harness(profile("cust-8", "tenant-apac-01"))

    outcomes = harness.planner.plan(batch_size=10, dry_run=False)

    assert outcomes[0].action is MigrationAction.SKIPPED
    assert outcomes[0].region is None
    assert outcomes[0].source_eligible_for_deletion is False
    assert harness.eu.count() == 0 and harness.us.count() == 0
    assert harness.reader.eligible_for_deletion() == frozenset()


def test_profile_with_no_region_assignment_is_skipped() -> None:
    harness = Harness(profile("cust-9", "tenant-absent-99"))

    outcomes = harness.planner.plan(batch_size=10, dry_run=False)

    assert outcomes[0].action is MigrationAction.SKIPPED
    assert harness.reader.remaining() == 1


def test_one_unroutable_profile_does_not_stop_the_batch() -> None:
    harness = Harness(
        profile("cust-10", "tenant-apac-01"),
        profile("cust-11", "tenant-eu-01"),
    )

    outcomes = harness.planner.plan(batch_size=10, dry_run=False)

    actions = {outcome.customer_id: outcome.action for outcome in outcomes}
    assert actions["cust-10"] is MigrationAction.SKIPPED
    assert actions["cust-11"] is MigrationAction.MIGRATED


def test_skip_reasons_do_not_disclose_profile_content() -> None:
    harness = Harness(profile("cust-12", "tenant-apac-01"))

    outcomes = harness.planner.plan(batch_size=10, dry_run=False)

    assert "ada.lovelace@example.test" not in outcomes[0].reason
    assert "Ada Lovelace" not in outcomes[0].reason
    assert "tenant-apac-01" in outcomes[0].reason


def test_digest_is_deterministic_and_content_sensitive() -> None:
    original = profile("cust-13", "tenant-eu-01")
    edited = LegacyProfile(
        customer_id=original.customer_id,
        tenant_id=original.tenant_id,
        email=original.email,
        display_name="Ada Byron",
        updated_at=original.updated_at,
    )

    assert profile_digest(original) == profile_digest(original)
    assert profile_digest(original) != profile_digest(edited)


def test_batch_size_limits_how_much_is_processed() -> None:
    harness = Harness(
        profile("cust-14", "tenant-eu-01"),
        profile("cust-15", "tenant-eu-01"),
        profile("cust-16", "tenant-us-01"),
    )

    outcomes = harness.planner.plan(batch_size=2, dry_run=False)

    assert len(outcomes) == 2
    assert harness.reader.remaining() == 1
