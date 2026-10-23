# Problem

Frozen checkout quotes could not be settled, uncertain provider outcomes could not be recovered, and
parking sessions had no safe paid-to-exit workflow that released derived occupancy.

# Change

- Add constrained UUID payment attempts and immutable one-per-quote settlements.
- Add a typed provider protocol and persistent deterministic simulator.
- Initiate provider calls between two short transactions and centralize result processing.
- Add explicit zero-charge settlement and manual reconciliation.
- Add ownership-scoped payment list/detail APIs.
- Extend sessions with exit attribution and atomic `PAID → CLOSED` exit.
- Preserve occupancy through `PAID`; release it only through existing open-session semantics.
- Add OpenAPI descriptions, lifecycle/ER documentation, and local demo instructions.

# Validation

- `ruff check .`
- `ruff format --check .`
- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python manage.py spectacular --file <temporary-schema> --validate`
- `pytest`
- `docker build --target runtime -t parking-lot-api:phase6 .`

# Migrations

- `parking_payments.0001_initial` creates payment attempts, settlements, persistent simulator state,
  indexes, partial unique constraints, and financial checks.
- `parking_sessions.0002_*` adds nullable exit gate/actor fields and the strict exit-metadata lifecycle
  constraint. It refuses to fabricate attribution for pre-existing closed rows; those rows require
  verified operational remediation before migration.

# Risks

- The simulator is intentionally not representative of all real-provider consistency and delivery
  behavior.
- A pending attempt requires explicit reconciliation; automatic jobs and webhooks are not included.
- Migration stops when historical closed rows lack exit attribution rather than inventing audit data.
- Entry still uses the previously documented correctness-first lot-row lock.
