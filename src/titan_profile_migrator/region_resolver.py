"""Resolution of the region a tenant's profiles belong in."""

from __future__ import annotations

from collections.abc import Mapping

from .models import HomeRegion, UnknownTenantError, UnsupportedRegionError


class TenantRegionResolver:
    """Maps a tenant onto its assigned region.

    Assignments arrive as raw strings from tenant onboarding, so this is the
    validation boundary. Resolution fails closed: an unknown tenant or an
    unrecognised region stops the profile from being migrated rather than
    sending it to a default estate.
    """

    def __init__(self, assignments: Mapping[str, str]) -> None:
        self._assignments = dict(assignments)

    def resolve(self, tenant_id: str) -> HomeRegion:
        try:
            assigned = self._assignments[tenant_id]
        except KeyError:
            raise UnknownTenantError(tenant_id) from None

        try:
            return HomeRegion(assigned)
        except ValueError:
            raise UnsupportedRegionError(tenant_id, assigned) from None
