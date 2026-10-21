# Parking Lot Management API

A Django 5.2 LTS and Django REST Framework modular monolith running on Python 3.12 and PostgreSQL.
Phase 3 adds parking-lot configuration and customer-owned vehicle records to the Phase 2 JWT and
user-management foundation. Entry, allocation, parking sessions, pricing, payments, Redis, and
Celery remain outside this phase.

Interactive OpenAPI documentation is available at `/api/v1/docs/`; the schema is available at
`/api/v1/schema/`.

## Structure and request flow

- `config/settings/`: shared, local, test, and fail-fast production configuration.
- `config/api/`: cross-application HTTP behavior, including consistent errors and liveness.
- `apps/accounts/api/`: thin HTTP views, request serializers, and route definitions.
- `apps/accounts/services/`: registration, user update, password, and token-revocation use cases.
- `apps/accounts/selectors.py`: user-list read queries and filters.
- `apps/accounts/permissions.py`: reusable application-role authorization.
- `apps/parking/`: constrained parking models, configuration/vehicle APIs, selectors, services, and
  the idempotent demo-data command.
- `apps/<module>/`: accounts, parking, sessions, pricing, payments, reporting, and audit boundaries.
  Empty modules remain intentional Phase 1/2 skeletons.
- `tests/` and application `tests/` packages: PostgreSQL model, API, authentication, authorization,
  ownership, constraint, and query-count tests.
- `docs/decisions/`: architecture and collaboration decisions.

The write path is **request → view → serializer → service → Django ORM/PostgreSQL → safe response
serializer**. Views own HTTP and permissions, serializers own input shape and validation, and
services coordinate state changes. Reads with meaningful filters go through selectors. This keeps
responsibilities clear without adding a generic repository over Django's ORM.

The project created its `AbstractUser` subclass in Phase 1 because changing `AUTH_USER_MODEL` after
other tables and production data refer to it is difficult. Phase 2 extends that stable model with
application roles and timestamps.

## Roles and Django privilege flags

| Account type | Self profile | Future parking operations | Manage non-admin users | Django admin site |
| --- | --- | --- | --- | --- |
| CUSTOMER | Yes | No | No | Only if separately granted `is_staff` |
| OPERATOR | Yes | Reserved for later phases | No | Only if separately granted `is_staff` |
| ADMIN | Yes | Yes when implemented | Yes | Only if separately granted `is_staff` |
| Django superuser | Yes | Privileged override | Yes, but its record is API-edit protected | Yes |

`role` expresses business authority. `is_staff` controls access to Django's admin UI, while
`is_superuser` is Django's privileged override. Creating an application ADMIN does not set either
Django flag. A PostgreSQL check constraint accepts only `ADMIN`, `OPERATOR`, or `CUSTOMER`.

## Phase 3 permissions

| API area | ADMIN | OPERATOR | CUSTOMER |
| --- | --- | --- | --- |
| Parking configuration lists/details | Read/write | Read-only | No access |
| Own vehicles | Read/write | Own records only | Own records only |
| Other users' vehicles | No access in Phase 3 | No access | No access |

Django superusers retain the documented configuration override. Vehicle access remains owner-scoped
even for ADMIN and OPERATOR accounts. A cross-owner vehicle ID returns 404 rather than revealing that
the record exists.

## Local environment setup

Prerequisites: Python 3.12, Docker Desktop with Compose, and Git.

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The project and integration tests use PostgreSQL, not SQLite.

## Start containers and apply migrations

```powershell
docker compose up --build -d
docker compose ps
docker compose exec web python manage.py migrate
```

Open `http://localhost:8000/api/v1/health/live/` for liveness and
`http://localhost:8000/api/v1/docs/` for Swagger UI.

Compose bind-mounts the repository at `/app`, so local source changes are immediately visible in the
development container. The mount overlays the application directory copied into the image; rebuild
after dependency or Dockerfile changes. Migrations stay separate from web startup, especially in
production.

## Bootstrap administrators

Create an application ADMIN interactively (business administration, no Django flags):

```powershell
docker compose exec web python manage.py create_app_admin --username app-admin --email admin@example.com
```

Create a Django superuser for `/admin/` when needed:

```powershell
docker compose exec web python manage.py createsuperuser
```

There is deliberately no public endpoint for creating an ADMIN.

## Seed demo parking configuration

After migrations, create one demo lot with basement/ground floors, entry/exit gates, and a mixture
of motorcycle, compact, large, maintenance, and disabled spots:

```powershell
docker compose exec web python manage.py seed_parking
```

The command is idempotent. Repeated runs add missing demo records but do not overwrite matching
records that have been customized. It never creates users or passwords.

## Authentication examples

These examples assume the API is at `http://localhost:8000`. Substitute returned token values for
`<access-token>` and `<refresh-token>`.

Register a CUSTOMER:

```bash
curl -X POST http://localhost:8000/api/v1/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","first_name":"Alice","password":"C0mpl3x!Parking-2026","password_confirm":"C0mpl3x!Parking-2026"}'
```

Log in and receive an access/refresh pair:

```bash
curl -X POST http://localhost:8000/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"C0mpl3x!Parking-2026"}'
```

Rotate a refresh token (the submitted refresh token is blacklisted):

```bash
curl -X POST http://localhost:8000/api/v1/auth/token/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh":"<refresh-token>"}'
```

Read or update the authenticated profile:

```bash
curl http://localhost:8000/api/v1/users/me/ \
  -H "Authorization: Bearer <access-token>"

curl -X PATCH http://localhost:8000/api/v1/users/me/ \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{"first_name":"Alicia","last_name":"Example"}'
```

Change the password:

```bash
curl -X POST http://localhost:8000/api/v1/users/me/change-password/ \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{"current_password":"C0mpl3x!Parking-2026","new_password":"N3w!Parking-Password-2026","new_password_confirm":"N3w!Parking-Password-2026"}'
```

Log out by blacklisting the caller-owned refresh token:

```bash
curl -X POST http://localhost:8000/api/v1/auth/logout/ \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{"refresh":"<refresh-token>"}'
```

Logout and password changes revoke refresh tokens. A stateless access token already issued remains
valid until its configured short expiry (15 minutes by default). Role and active status are not
trusted from token claims: authentication reloads the user, so role changes and deactivation apply
to existing access tokens on the next request.

Registration and token acquisition use configurable DRF throttles. These are application-level
controls and do not replace production rate limiting at a reverse proxy, API gateway, or firewall.

## Parking configuration examples

Create a parking lot as an ADMIN:

```bash
curl -X POST http://localhost:8000/api/v1/parking-lots/ \
  -H "Authorization: Bearer <admin-access-token>" \
  -H "Content-Type: application/json" \
  -d '{"code":"blr-central","name":"Bengaluru Central","address":"MG Road","timezone":"Asia/Kolkata"}'
```

Create a compact spot after creating its floor:

```bash
curl -X POST http://localhost:8000/api/v1/spots/ \
  -H "Authorization: Bearer <admin-access-token>" \
  -H "Content-Type: application/json" \
  -d '{"floor":1,"number":"b1-c-01","spot_type":"COMPACT","operational_status":"ENABLED"}'
```

List configuration as ADMIN or OPERATOR with validated filters:

```bash
curl "http://localhost:8000/api/v1/spots/?parking_lot=1&spot_type=COMPACT&operational_status=ENABLED" \
  -H "Authorization: Bearer <access-token>"
```

`ENABLED` describes operational configuration; it does not mean unoccupied. Occupancy will come
from active parking sessions in Phase 4. Physical capacity is derived from spot rows rather than a
manually editable counter. Deactivating a lot or floor preserves descendants but makes them
effectively unavailable.

An ADMIN spot-creation request follows this path:

```text
POST /api/v1/spots/
→ JWT loads the current database user
→ configuration permission requires ADMIN or superuser
→ serializer validates floor ID, number, type, and operational status
→ service locks and verifies the active floor and lot
→ model normalizes the number
→ PostgreSQL enforces enum, nonblank, and floor-scoped uniqueness constraints
→ output serializer returns the safe spot representation with HTTP 201
```

A known uniqueness race is translated to a sanitized HTTP 409 response; raw PostgreSQL errors are
never returned.

## Vehicle examples

Associate a vehicle with the authenticated account:

```bash
curl -X POST http://localhost:8000/api/v1/vehicles/ \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{"registration_number":"ka-01 ab 1234","vehicle_type":"CAR"}'
```

The stored form is `KA01AB1234`: surrounding whitespace is trimmed, letters are uppercased, and
spaces/hyphens are removed. This normalization is not claimed to validate every real-world plate
format. The owner is always taken from the access token; client-supplied owners are rejected.

```bash
curl "http://localhost:8000/api/v1/vehicles/?is_active=true" \
  -H "Authorization: Bearer <access-token>"

curl -X PATCH http://localhost:8000/api/v1/vehicles/1/ \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{"vehicle_type":"CAR","is_active":false}'
```

Vehicle ownership means association with an application account, not verified legal ownership.
The Phase 3 decisions and ER diagram are in
[ADR 0003](docs/decisions/0003-parking-configuration-and-vehicles.md).

## Errors

API failures use a consistent envelope. Validation failures include field details:

```json
{
  "error": {
    "code": "validation_error",
    "detail": "Request validation failed.",
    "fields": {"username": ["A user with that username already exists."]}
  }
}
```

Invalid input returns 400, missing/invalid authentication 401, insufficient application authority
403, missing resources 404, and known normalized uniqueness conflicts 409.

## Tests and quality checks

```powershell
docker compose exec web pytest
docker compose exec web ruff check .
docker compose exec web ruff format --check .
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
```

To apply formatting intentionally:

```powershell
docker compose exec web ruff format .
```

## Stop services

```powershell
docker compose down
```

## Destructive: reset all local database data

This permanently deletes the named PostgreSQL volume and every local row:

```powershell
docker compose down --volumes
```

Start again and explicitly apply migrations afterward.

## Production configuration

Use `config.settings.production`. It refuses to start unless `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS`, and every `POSTGRES_*` connection variable are present. Supply secrets from
the deployment environment or secret manager; never commit `.env`. The production image starts
Gunicorn and does not run migrations automatically.

## Git workflow

Use short-lived feature branches, pull requests, passing CI, and squash merges. Instructions for an
authorized maintainer to require the CI job on `main` are in
[ADR 0002](docs/decisions/0002-git-workflow.md). Never claim a remote rule, push, merge, or
deployment occurred without verifying it.

