"""Planning and execution of a migration batch."""

from __future__ import annotations

from collections.abc import Sequence

from .batch_migrator import BatchMigrator
from .legacy_reader import LegacyReader
from .models import MigrationOutcome


class MigrationPlanner:
    """Reads a batch out of the shared global store and migrates each profile.

    A dry run reports exactly what a real run would do without writing
    anything, so the plan can be reviewed before any data moves.
    """

    def __init__(self, reader: LegacyReader, migrator: BatchMigrator) -> None:
        self._reader = reader
        self._migrator = migrator

    def plan(self, *, batch_size: int, dry_run: bool = True) -> Sequence[MigrationOutcome]:
        batch = self._reader.read_batch(batch_size)
        return [self._migrator.migrate(profile, dry_run=dry_run) for profile in batch]
