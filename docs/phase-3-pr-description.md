# Phase 3 PR description

## Problem

The authenticated foundation cannot yet describe physical parking infrastructure or associate
vehicles with customer accounts.

## Change

- Add parking lots, floors, gates, spots, and account-associated vehicles with normalized identifiers,
  timestamps, protected relationships, PostgreSQL constraints, and filter-driven indexes.
- Add paginated configuration APIs: ADMIN read/write, OPERATOR read-only, CUSTOMER denied, with the
  existing Django-superuser override.
- Add owner-scoped vehicle APIs that assign ownership from authentication and return 404 across
  account boundaries.
- Translate known uniqueness races into sanitized 409 responses.
- Add an idempotent `seed_parking` command that preserves customized matching records.
- Document the API, permissions, ER model, effective availability, derived capacity, and ownership
  scope.

## Validation

- `ruff check .`
- `ruff format --check .`
- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python manage.py spectacular --file NUL --validate`
- `pytest`
- `docker build --target runtime -t parking-lot-api:phase3 .`

## Migrations

- Create `ParkingLot`, `Floor`, `Gate`, `ParkingSpot`, and `Vehicle` tables.
- Add named uniqueness/nonblank/enum check constraints.
- Add composite indexes for spot configuration filters and owner-active vehicle lists.

Apply migrations as a separate deployment step before serving the new API.

## Risks

- Registration normalization intentionally covers formatting variants, not every jurisdiction's
  plate syntax.
- Vehicle ownership represents account association, not verified legal ownership.
- Operationally enabled spots are not necessarily unoccupied; live occupancy begins in Phase 4.
- Deactivation preserves descendants, so consumers must use the documented effective-state fields.

