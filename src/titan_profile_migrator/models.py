"""Value types and failures for the Titan profile migration.

Beaconstone Financial moved customer profile storage into per-region estates.
Profiles written before that change still sit in the shared global store, and
this package relocates them into the estate assigned to their tenant.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HomeRegion(str, Enum):
    """A region Beaconstone operates profile storage in."""

    EU = "EU"
    US = "US"


@dataclass(frozen=True)
class LegacyProfile:
    """A profile as held in the shared global store."""

    customer_id: str
    tenant_id: str
    email: str
    display_name: str
    updated_at: str


@dataclass(frozen=True)
class RegionalCopy:
    """A profile written into a regional estate, with its content digest."""

    customer_id: str
    tenant_id: str
    region: HomeRegion
    digest: str
    written_at: str


class MigrationAction(str, Enum):
    """What the migrator did, or would do, with one profile."""

    PLANNED = "planned"
    MIGRATED = "migrated"
    ALREADY_MIGRATED = "already-migrated"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class MigrationOutcome:
    """The auditable result for one profile.

    Carries identifiers and a decision only. The email address and display
    name being relocated are never recorded here.
    """

    customer_id: str
    tenant_id: str
    region: HomeRegion | None
    action: MigrationAction
    reason: str
    source_eligible_for_deletion: bool


class MigrationError(Exception):
    """Base failure. Messages carry identifiers, never profile content."""


class UnknownTenantError(MigrationError):
    """The tenant has no region assignment on file."""

    def __init__(self, tenant_id: str) -> None:
        super().__init__(f"Tenant {tenant_id} has no home region assignment")
        self.tenant_id = tenant_id


class UnsupportedRegionError(MigrationError):
    """The tenant is assigned to a region Beaconstone does not operate."""

    def __init__(self, tenant_id: str, assigned_region: str) -> None:
        super().__init__(
            f"Tenant {tenant_id} is assigned to unsupported region {assigned_region}"
        )
        self.tenant_id = tenant_id
        self.assigned_region = assigned_region


class VerificationError(MigrationError):
    """The regional copy does not match the profile it was made from."""

    def __init__(self, customer_id: str, expected: str, actual: str) -> None:
        super().__init__(
            f"Regional copy of {customer_id} failed verification "
            f"(expected digest {expected}, found {actual})"
        )
        self.customer_id = customer_id
        self.expected = expected
        self.actual = actual
