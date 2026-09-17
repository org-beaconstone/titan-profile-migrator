"""Residence rules and placement reporting."""

from __future__ import annotations

from titan_profile_migrator import (
    SHARED_ESTATE,
    HomeRegion,
    LegacyProfile,
    LegacyReader,
    PlacementReport,
    ResidencePolicy,
    TenantRegionResolver,
)

ASSIGNMENTS = {
    "tenant-eu-01": "EU",
    "tenant-us-01": "US",
    "tenant-apac-01": "APAC",
}


def record(identifier: str, tenant_id: str) -> LegacyProfile:
    return LegacyProfile(
        customer_id=identifier,
        tenant_id=tenant_id,
        email="ada.lovelace@example.test",
        display_name="Ada Lovelace",
        updated_at="2026-03-02T09:00:00+00:00",
    )


def build_report(*records: LegacyProfile) -> PlacementReport:
    return PlacementReport(
        LegacyReader(records),
        TenantRegionResolver(ASSIGNMENTS),
        ResidencePolicy(),
    )


class TestResidencePolicy:
    def test_permits_only_the_estate_serving_the_locality(self) -> None:
        policy = ResidencePolicy()

        assert policy.permitted_estate(HomeRegion.EU) == "eu-primary"
        assert policy.permitted_estate(HomeRegion.US) == "us-primary"
        assert policy.permits(HomeRegion.EU, "eu-primary")
        assert not policy.permits(HomeRegion.EU, "us-primary")

    def test_refuses_the_shared_estate_for_every_locality(self) -> None:
        policy = ResidencePolicy()

        assert not policy.permits(HomeRegion.EU, SHARED_ESTATE)
        assert not policy.permits(HomeRegion.US, SHARED_ESTATE)
        assert policy.is_outside_every_locality(SHARED_ESTATE)
        assert not policy.is_outside_every_locality("eu-primary")

    def test_enumerates_the_footprint(self) -> None:
        assert sorted(ResidencePolicy().footprint()) == [
            (HomeRegion.EU, "eu-primary"),
            (HomeRegion.US, "us-primary"),
        ]


class TestPlacementReport:
    def test_reports_the_target_estate_for_each_tenant(self) -> None:
        report = build_report(record("p-1", "tenant-eu-01"), record("p-2", "tenant-us-01"))

        rows = {row.tenant_id: row for row in report.rows(batch_size=10)}

        assert rows["tenant-eu-01"].target_estate == "eu-primary"
        assert rows["tenant-us-01"].target_estate == "us-primary"
        assert all(row.current_estate == SHARED_ESTATE for row in rows.values())

    def test_counts_records_awaiting_relocation_per_tenant(self) -> None:
        report = build_report(
            record("p-1", "tenant-eu-01"),
            record("p-2", "tenant-eu-01"),
            record("p-3", "tenant-us-01"),
        )

        rows = {row.tenant_id: row for row in report.rows(batch_size=10)}

        assert rows["tenant-eu-01"].awaiting_relocation == 2
        assert rows["tenant-us-01"].awaiting_relocation == 1

    def test_records_in_the_shared_estate_are_reported_as_misplaced(self) -> None:
        report = build_report(record("p-1", "tenant-eu-01"))

        misplaced = report.misplaced(batch_size=10)

        assert [row.tenant_id for row in misplaced] == ["tenant-eu-01"]
        assert misplaced[0].is_misplaced

    def test_tenant_without_a_settled_locality_is_reported(self) -> None:
        report = build_report(
            record("p-1", "tenant-apac-01"), record("p-2", "tenant-absent-99")
        )

        unsettled = report.unsettled(batch_size=10)

        assert {row.tenant_id for row in unsettled} == {"tenant-apac-01", "tenant-absent-99"}
        assert all(row.problem is not None for row in unsettled)
        assert all(not row.is_misplaced for row in unsettled)

    def test_report_rows_disclose_no_personal_details(self) -> None:
        report = build_report(record("p-1", "tenant-eu-01"))

        rendered = repr(report.rows(batch_size=10))

        assert "ada.lovelace@example.test" not in rendered
        assert "Ada Lovelace" not in rendered
