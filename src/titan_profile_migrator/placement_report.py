"""Reporting on where account holders' personal details currently reside.

Before a migration window, reviewers need to know which machines still hold
personal information outside the locality that ought to keep it. This report
answers that without moving anything: for each tenant with records still in the
shared estate, it names the locality the tenant was onboarded into and the
estate that should hold those records once the move completes.

It reads the same locality assignments the migrator reads, so a line in this
report describes where a real run would place the records. Placement only is
reported — no personal details appear in a report row.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from .legacy_reader import LegacyReader
from .models import HomeRegion, MigrationError
from .region_resolver import TenantRegionResolver
from .residence_policy import SHARED_ESTATE, ResidencePolicy


class PlacementRow(NamedTuple):
    """Where one tenant's records sit now, and where they belong."""

    tenant_id: str
    awaiting_relocation: int
    current_estate: str
    target_locality: HomeRegion | None
    target_estate: str | None
    problem: str | None

    @property
    def is_misplaced(self) -> bool:
        """Whether these records are held outside the tenant's own locality."""
        return self.target_estate is not None and self.current_estate != self.target_estate


class PlacementReport:
    """Describes the current position of records awaiting relocation."""

    def __init__(
        self,
        reader: LegacyReader,
        resolver: TenantRegionResolver,
        policy: ResidencePolicy,
    ) -> None:
        self._reader = reader
        self._resolver = resolver
        self._policy = policy

    def rows(self, batch_size: int) -> Sequence[PlacementRow]:
        """One row per tenant still holding records in the shared estate."""
        awaiting: dict[str, int] = {}
        for record in self._reader.read_batch(batch_size):
            awaiting[record.tenant_id] = awaiting.get(record.tenant_id, 0) + 1
        return [self._row_for(tenant_id, count) for tenant_id, count in sorted(awaiting.items())]

    def misplaced(self, batch_size: int) -> Sequence[PlacementRow]:
        """Rows for records held outside the locality that should keep them."""
        return [row for row in self.rows(batch_size) if row.is_misplaced]

    def unsettled(self, batch_size: int) -> Sequence[PlacementRow]:
        """Rows whose destination locality could not be settled."""
        return [row for row in self.rows(batch_size) if row.target_estate is None]

    def _row_for(self, tenant_id: str, awaiting: int) -> PlacementRow:
        try:
            locality = self._resolver.resolve(tenant_id)
        except MigrationError as failure:
            return PlacementRow(
                tenant_id=tenant_id,
                awaiting_relocation=awaiting,
                current_estate=SHARED_ESTATE,
                target_locality=None,
                target_estate=None,
                problem=str(failure),
            )
        return PlacementRow(
            tenant_id=tenant_id,
            awaiting_relocation=awaiting,
            current_estate=SHARED_ESTATE,
            target_locality=locality,
            target_estate=self._policy.permitted_estate(locality),
            problem=None,
        )
