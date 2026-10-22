# Problem

The backend has parking configuration and registered vehicles but cannot safely admit a vehicle,
allocate compatible capacity, issue a ticket, or report live availability.

# Change

- Add `ParkingSession` with lifecycle checks, snapshots, unguessable ticket references, protected
  relationships, and PostgreSQL partial unique constraints for open vehicle/spot sessions.
- Add deterministic compatibility allocation through an injected Strategy and a locking repository.
- Add transactional ADMIN/OPERATOR entry at `POST /api/v1/parking-sessions/entry/`.
- Add ownership-scoped session reads and authenticated aggregate availability.
- Serialize entry and relevant configuration changes per lot; block occupied vehicle/spot identity
  changes while allowing operational spot status changes.
- Document lock order, occupancy semantics, availability semantics, request flow, and ER changes.

# Validation

- `ruff check .`
- `ruff format --check .`
- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python manage.py spectacular --file schema.yml --validate`
- `pytest`
- Docker production image build

The suite includes transaction-enabled, barrier-coordinated PostgreSQL concurrency tests for one
spot/two vehicles, duplicate vehicle entry, cross-lot duplicate entry, and entry/configuration races.

# Migrations

`apps/sessions/migrations/0001_initial.py` creates the parking-session table, indexes, lifecycle
checks, ticket uniqueness, and partial unique constraints. Apply explicitly with:

```powershell
docker compose exec web python manage.py migrate
```

# Risks

- The lot row intentionally serializes entry and configuration operations for correctness. This
  limits per-lot throughput and should be replaced only after measuring contention.
- Availability is a point-in-time informational view, not a reservation guarantee.
- Phase 4 intentionally has no idempotency key; a repeated successful entry conflicts safely.
- Exit, checkout, pricing, payments, Redis, and Celery are not part of this change.
