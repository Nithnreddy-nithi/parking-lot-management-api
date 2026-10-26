# Problem

Sessions currently have no historical rate, deterministic fee calculation, or retry-safe checkout.
Using the current active rate later would allow policy changes to rewrite charges for parked
vehicles.

# Change

- Add immutable, versioned policies with one active version per lot and vehicle type.
- Capture a one-to-one pricing snapshot atomically at entry.
- Add pure `HOURLY_V1` Decimal calculation with grace threshold, upward hourly rounding, rolling
  24-hour caps, and a bounded breakdown.
- Add one immutable checkout quote per session and transition `ACTIVE → PAYMENT_PENDING` without
  releasing occupancy.
- Add ADMIN policy APIs, staff checkout, ownership-scoped quote reads, explicit legacy backfill, and
  idempotent demo pricing.

# Validation

- `ruff check .`
- `ruff format --check .`
- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python manage.py spectacular --file schema.yml --validate`
- `pytest`
- `docker build --target runtime -t parking-lot-api:phase5 .`

Tests cover calculator boundaries and timezone behavior, policy publication and constraints,
entry snapshots, legacy migration, checkout retries/permissions/ownership, and coordinated
PostgreSQL checkout concurrency.

# Migrations

`apps/pricing/migrations/0001_initial.py` creates policies, snapshots, quotes, financial checks,
version uniqueness, active-policy partial uniqueness, and one-to-one session constraints.

Apply separately from web startup:

```powershell
docker compose exec web python manage.py migrate
```

# Risks

- Checkout intentionally freezes future parking accrual; quote expiry and exit-delay pricing are not
  implemented.
- Existing sessions require an explicitly selected historical policy before checkout.
- Lot locks favor correctness over maximum publication/entry/checkout throughput.
- Payments, exit, webhooks, refunds, Redis, and Celery are not part of this change.
