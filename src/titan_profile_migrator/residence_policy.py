"""Rules for where an account holder's personal details may be kept.

Beaconstone Financial holds each party's personal information inside the
footprint their tenant was onboarded into. A record belonging to a European
tenant resides on European hardware; one belonging to a United States tenant
resides on United States hardware. Neither is duplicated into the other
footprint.

The shared estate that predates per-locality persistence sits outside every
footprint. Records there are the backlog this package exists to clear, and
nothing may newly be placed in it.

These rules are the statement of what is permitted. The migrator is the
machinery that obeys them, and the placement report reads them to describe the
current position without moving anything.
"""

from __future__ import annotations

from .models import HomeRegion

#: The estate that keeps records for each locality.
ESTATE_BY_LOCALITY: dict[HomeRegion, str] = {
    HomeRegion.EU: "eu-primary",
    HomeRegion.US: "us-primary",
}

#: The shared estate that sits outside every locality.
SHARED_ESTATE = "global-primary"


class ResidencePolicy:
    """Where records belonging to a locality are permitted to live."""

    def permitted_estate(self, locality: HomeRegion) -> str:
        """The only estate a record from this locality may reside in."""
        return ESTATE_BY_LOCALITY[locality]

    def permits(self, locality: HomeRegion, estate: str) -> bool:
        """Whether a record from ``locality`` may be held in ``estate``.

        False for every estate outside the locality, the shared estate
        included, so a caller cannot satisfy the policy by widening where it
        writes.
        """
        return estate == self.permitted_estate(locality)

    def is_outside_every_locality(self, estate: str) -> bool:
        """Whether an estate sits outside all operated footprints."""
        return estate not in ESTATE_BY_LOCALITY.values()

    def footprint(self) -> list[tuple[HomeRegion, str]]:
        """Every locality records are kept in, with the estate holding them."""
        return [(locality, estate) for locality, estate in ESTATE_BY_LOCALITY.items()]
