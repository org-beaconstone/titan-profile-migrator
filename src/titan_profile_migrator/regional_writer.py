"""Writers for the per-region profile estates."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from .models import HomeRegion, LegacyProfile, RegionalCopy, UnsupportedRegionError


class RegionalPartitionWriter(Protocol):
    """One region's estate."""

    @property
    def region(self) -> HomeRegion: ...

    def write(self, profile: LegacyProfile, digest: str, written_at: str) -> RegionalCopy: ...

    def find(self, customer_id: str) -> RegionalCopy | None: ...


class InMemoryPartitionWriter:
    """Estate backed by a dictionary, for dry runs and local verification."""

    def __init__(self, region: HomeRegion) -> None:
        self._region = region
        self._copies: dict[str, RegionalCopy] = {}

    @property
    def region(self) -> HomeRegion:
        return self._region

    def write(self, profile: LegacyProfile, digest: str, written_at: str) -> RegionalCopy:
        copy = RegionalCopy(
            customer_id=profile.customer_id,
            tenant_id=profile.tenant_id,
            region=self._region,
            digest=digest,
            written_at=written_at,
        )
        self._copies[profile.customer_id] = copy
        return copy

    def find(self, customer_id: str) -> RegionalCopy | None:
        return self._copies.get(customer_id)

    def count(self) -> int:
        return len(self._copies)


class RegionalWriter:
    """Selects the estate a profile should be written into."""

    def __init__(self, partitions: Iterable[RegionalPartitionWriter]) -> None:
        self._partitions = {partition.region: partition for partition in partitions}

    def for_region(self, region: HomeRegion) -> RegionalPartitionWriter:
        """Returns the writer for the region, or fails.

        There is no fallback estate: a region with no configured writer stops
        the migration for that profile.
        """
        try:
            return self._partitions[region]
        except KeyError:
            raise UnsupportedRegionError("<unconfigured>", region.value) from None
