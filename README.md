# titan-profile-migrator

Relocates Titan customer profiles out of Beaconstone Financial's shared global
profile store and into the estate assigned to each tenant's region.

Profiles written before regional storage existed still sit in the shared global
store. This tool places a verified copy in the right region and only then marks
the source as safe to remove.

> Fictional tooling used for demonstration purposes. It contains no real
> customer records, credentials, or service endpoints.

## Migration

```
MigrationPlanner.plan
  -> LegacyReader.read_batch                    reads from the shared global store
  -> BatchMigrator.migrate
     -> TenantRegionResolver.resolve            fails closed on unknown regions
     -> RegionalWriter.for_region               no fallback estate
     -> Verifier.verify                         deterministic content digest
     -> LegacyReader.mark_eligible_for_deletion only after verification
```

## Guarantees

- **Read-only at the source.** The migrator never deletes. It marks a profile
  eligible for deletion, and removal is a separate, later operation, so a
  failed run can always be retried against untouched source data.
- **Verified before cleared.** A source profile is only marked deletable once
  the regional copy's digest matches the source. If verification fails, the
  source is left exactly as it was.
- **Deterministic dry run.** `plan(dry_run=True)` reports precisely what a real
  run would do and writes nothing. Repeating it leaves the batch unchanged.
- **Idempotent retry.** A profile that already has a verified regional copy is
  reported as `already-migrated` rather than written a second time. Because
  `read_batch` excludes profiles already cleared for deletion, a repeated run
  resumes where the last one stopped.
- **Fails closed.** A tenant with no assignment, or one assigned to a region
  Beaconstone does not operate, is skipped and reported. One unroutable profile
  does not stop the rest of the batch.
- **Redacted reporting.** `MigrationOutcome` carries identifiers and a
  decision. The email address and display name being relocated never appear in
  an outcome, a reason string, or an exception message.

## Commands

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

Requires Python 3.11 or newer. There are no runtime dependencies.
