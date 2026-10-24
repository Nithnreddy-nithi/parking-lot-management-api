# Parking Lot Management API

A Django 5.2 LTS and Django REST Framework modular monolith running on Python 3.12 and PostgreSQL.
Phase 6 provides payment settlement and atomic vehicle exit. The payment boundary now supports both
the persistent local simulator and Razorpay Standard Checkout, including signed confirmation,
verified idempotent webhooks, reconciliation, and full or partial refunds. Redis and Celery remain
outside the current scope.

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
- `apps/sessions/`: session lifecycle data, allocation policy, locking repository, entry, checkout,
  and exit coordination, scoped read selectors, availability aggregation, APIs, and concurrency
  tests.
- `apps/pricing/`: versioned policies, immutable snapshots and quotes, pure fee calculators,
  pricing-management APIs, selectors, and legacy backfill tooling.
- `apps/payments/`: payment attempts, immutable settlements, refund ledger, provider protocol,
  simulator and Razorpay adapters, signed webhook handling, reconciliation, scoped APIs, and tests.
- `apps/<module>/`: accounts, parking, sessions, pricing, payments, reporting, and audit boundaries.
  Reporting and audit remain intentional skeletons for later phases.
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

| Account type | Self profile | Parking entry | Manage non-admin users | Django admin site |
| --- | --- | --- | --- | --- |
| CUSTOMER | Yes | No | No | Only if separately granted `is_staff` |
| OPERATOR | Yes | Yes | No | Only if separately granted `is_staff` |
| ADMIN | Yes | Yes | Yes | Only if separately granted `is_staff` |
| Django superuser | Yes | Privileged override | Yes, but its record is API-edit protected | Yes |

`role` expresses business authority. `is_staff` controls access to Django's admin UI, while
`is_superuser` is Django's privileged override. Creating an application ADMIN does not set either
Django flag. A PostgreSQL check constraint accepts only `ADMIN`, `OPERATOR`, or `CUSTOMER`.

## Parking permissions

| API area | ADMIN | OPERATOR | CUSTOMER |
| --- | --- | --- | --- |
| Parking configuration lists/details | Read/write | Read-only | No access |
| Own vehicles | Read/write | Own records only | Own records only |
| Other users' vehicle CRUD | No access | No access | No access |
| Admit a registered vehicle | Yes | Yes | No |
| Session reads | All | All | Own vehicles only |
| Availability summary | Yes | Yes | Yes |
| Pricing policy management | Read/write | No | No |
| Checkout | Yes | Yes | No |
| Quote reads | All | All | Own vehicles only |
| Initiate payment | All sessions | All sessions | Own vehicles only |
| Settle zero quote | All sessions | All sessions | Own vehicles only |
| Payment reads | All | All | Own vehicles only |
| Refund reads | All | All | Own payments only |
| Issue refund | Yes | No | No |
| Record exit | Yes | Yes | No |

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

After migrations and ADMIN creation, create demo configuration and one initial INR policy for every
vehicle type. The required username is recorded as the pricing creator; the command never creates a
user or password:

```powershell
docker compose exec web python manage.py seed_parking --created-by app-admin
```

The command is idempotent. Repeated runs add missing demo records but do not overwrite matching
configuration or any existing pricing history.

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

`ENABLED` describes operational configuration; it does not mean unoccupied. Occupancy is derived
from open parking sessions. Physical capacity is derived from spot rows rather than a manually
editable counter. Deactivating a lot or floor preserves descendants but makes them effectively
unavailable for new entry.

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
The configuration decisions are in
[ADR 0003](docs/decisions/0003-parking-configuration-and-vehicles.md).

## Vehicle entry and parking-session examples

An ADMIN or OPERATOR can admit any registered active vehicle through an active `ENTRY` or `BOTH`
gate. The server—not the client—chooses the spot, actor, entry time, initial status, snapshots, and
ticket reference:

```bash
curl -X POST http://localhost:8000/api/v1/parking-sessions/entry/ \
  -H "Authorization: Bearer <operator-access-token>" \
  -H "Content-Type: application/json" \
  -d '{"vehicle_id":1,"entry_gate_id":1}'
```

Compatibility is explicit: motorcycle uses motorcycle, car prefers compact then large, and truck
uses large. Candidates are then ordered by floor level, spot number, and spot ID. Floor level is a
deterministic rule, not a claim about physical distance from the gate. Repeating a successful entry
returns `VEHICLE_ALREADY_PARKED` and never creates a second open session.

Customers see only sessions associated with their vehicles; ADMIN and OPERATOR accounts see all:

```bash
curl "http://localhost:8000/api/v1/parking-sessions/?status=ACTIVE&lot=1&entry_date_from=2026-10-01" \
  -H "Authorization: Bearer <access-token>"
```

Only staff may add `vehicle=<id>` to that query. Filters are strict, results are paginated, and
ordering is newest `entered_at` then ID. No session `PATCH` or `DELETE` API exists.

Any authenticated user can read counts without customer or registration details:

```bash
curl http://localhost:8000/api/v1/parking-lots/1/availability/ \
  -H "Authorization: Bearer <access-token>"
```

`operationally_enabled` counts configured `ENABLED` spots. `occupied` means an open session exists,
including on a maintenance spot. `available` additionally requires active parents and no open
session. Availability is informational and never reserves capacity; only transactional entry does.

The entry request path is:

```text
POST /api/v1/parking-sessions/entry/
→ JWT authentication and ADMIN/OPERATOR permission
→ strict serializer accepts only vehicle_id and entry_gate_id
→ entry service opens one PostgreSQL transaction
→ repository locks lot → gate → vehicle → active pricing policy → selected spot
→ allocation policy applies compatibility and deterministic preference
→ service rechecks eligibility and creates the ACTIVE session and immutable pricing snapshot
→ PostgreSQL partial unique constraints guard vehicle and spot
→ safe ticket serializer returns HTTP 201
```

Lot-row serialization is deliberately correctness-first and limits parallel entry throughput within
one lot. It can be replaced with finer-grained locking after measurement. The lock protocol,
partial constraints, updated ER diagram, and sequence diagram are in
[ADR 0004](docs/decisions/0004-transactional-entry-and-availability.md).

## Pricing and checkout

ADMIN publishes a new server-versioned policy. Publication retires the previous active version for
the same lot and vehicle type in one transaction:

```bash
curl -X POST http://localhost:8000/api/v1/pricing-policies/ \
  -H "Authorization: Bearer <admin-access-token>" \
  -H "Content-Type: application/json" \
  -d '{"parking_lot":1,"vehicle_type":"CAR","currency":"INR","hourly_rate":"30.00","grace_minutes":15,"daily_cap":"300.00"}'
```

Published financial fields are immutable. Rate changes create version 2, version 3, and so on.
Entry selects pricing by vehicle type—not allocated spot type—and copies the policy into a snapshot
in the same transaction as the session. If pricing is missing, entry returns
`PRICING_NOT_CONFIGURED` without creating a partial session.

ADMIN or OPERATOR freezes the amount due with:

```bash
curl -X POST http://localhost:8000/api/v1/parking-sessions/1/checkout/ \
  -H "Authorization: Bearer <operator-access-token>" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Checkout uses elapsed UTC duration, checks grace once, rounds every started hour upward, and applies
the daily cap to consecutive 24-hour blocks from entry. It creates one immutable quote and changes
`ACTIVE` to `PAYMENT_PENDING`. Repeated calls return that original quote and timestamp. The amount
does not continue accruing after checkout in this product version.

Checkout does not close the session, set `closed_at`, mark it paid, or release its spot. A
zero-charge quote remains `PAYMENT_PENDING` until the explicit zero-charge settlement operation.

Customers can read a quote only for their own session:

```bash
curl http://localhost:8000/api/v1/parking-sessions/1/quote/ \
  -H "Authorization: Bearer <access-token>"
```

Sessions created before Phase 5 deliberately have no invented price. Select the historically
correct policy explicitly and optionally restrict the affected session IDs:

```powershell
docker compose exec web python manage.py backfill_pricing_snapshots `
  --policy-id 7 --session-id 101 --session-id 102
```

The command is idempotent and never overwrites a snapshot. Until backfilled, checkout returns
`SESSION_PRICING_NOT_CONFIGURED`. Pricing decisions, the updated ER diagram, and checkout sequence
are in [ADR 0005](docs/decisions/0005-versioned-pricing-and-checkout.md).

## Payments, settlement, refunds, and exit

A payment attempt records one interaction with the configured provider. A settlement is the single
authoritative proof that the frozen quote has been paid. Failed attempts remain as history, while a
quote has at most one successful attempt and one settlement. Clients supply only the parking
session ID; amount, currency, merchant reference, and status are server-controlled.

The local simulator is persistent in PostgreSQL rather than process memory, so repeated HTTP
requests and different web workers observe the same provider-side result for an attempt UUID. Set
`SIMULATED_PAYMENT_SCENARIO` in `.env` to `SUCCESS`, `FAILURE`, `PENDING`, or
`TIMEOUT_AFTER_SUCCESS`, then restart the web process. This development control is never accepted
from the public payment API.

### Razorpay Test Mode configuration

The backend integrates Razorpay through the official Python SDK. It creates a Razorpay Order; card,
UPI, wallet, and bank credentials stay inside Razorpay Standard Checkout and never pass through this
API. Start in Razorpay **Test Mode**, create API keys and a separate webhook secret, then set:

```dotenv
PAYMENT_PROVIDER=RAZORPAY
RAZORPAY_KEY_ID=rzp_test_replace_me
RAZORPAY_KEY_SECRET=replace_me
RAZORPAY_WEBHOOK_SECRET=replace_me_with_a_different_secret
```

Rebuild after adding the SDK, then restart the services:

```powershell
docker compose up --build -d
docker compose exec web python manage.py migrate
```

Configure this HTTPS webhook URL in the Razorpay Dashboard:

```text
https://<your-host>/api/v1/payments/webhooks/razorpay/
```

Subscribe to `payment.captured`, `payment.failed`, `refund.created`, `refund.processed`, and
`refund.failed` where available. The handler validates `X-Razorpay-Signature` against the exact raw
request body, requires `X-Razorpay-Event-Id`, and stores only event metadata plus a SHA-256 payload
digest—not card data or the full webhook payload. Test and live dashboard modes need separate keys
and webhook configuration.

Initiate or reuse a payment for a positive frozen quote:

```bash
curl -X POST http://localhost:8000/api/v1/payments/ \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{"parking_session_id":1}'
```

With Razorpay selected, a pending response includes the safe public `checkout_key_id` and
`provider_order_reference`. Pass those values, amount, and currency to Razorpay Standard Checkout.
After Checkout returns its three signed values, confirm them server-side:

```bash
curl -X POST http://localhost:8000/api/v1/payments/<attempt-uuid>/confirm/ \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{"razorpay_order_id":"order_...","razorpay_payment_id":"pay_...","razorpay_signature":"..."}'
```

Signature verification alone does not settle the quote. The adapter fetches the payment from
Razorpay and requires `captured` status with the exact frozen amount, currency, order, and merchant
reference. Webhooks provide the durable path if the browser closes before confirmation.

The service uses three boundaries:

```text
transaction 1: lock session → quote; create or reuse PENDING attempt; commit
outside transaction: call provider using attempt UUID as stable merchant reference
transaction 2: lock session → quote → attempt; validate result; settle and mark PAID; commit
```

No database lock is held across a provider call. A timeout is ambiguous: the provider may have
charged successfully even though the application received no response. The attempt therefore stays
`PENDING`; it is never treated as a confirmed failure or retried under a new merchant reference.
Recover the recorded simulator result through the same result-processing service:

```powershell
docker compose exec web python manage.py reconcile_payment <attempt-uuid>
```

For a Razorpay order-creation timeout, reconciliation searches by the unique receipt derived from
the unchanged attempt UUID, saves the recovered order ID, and then retrieves its payment. It never
creates a new merchant reference for an uncertain result.

Only an ADMIN can request a partial or full refund. Pending refunds reserve their amount under a
settlement row lock, preventing concurrent requests from exceeding the captured payment:

```bash
curl -X POST http://localhost:8000/api/v1/refunds/ \
  -H "Authorization: Bearer <admin-access-token>" \
  -H "Content-Type: application/json" \
  -d '{"payment_attempt_id":"<attempt-uuid>","amount":"25.00","reason":"Approved adjustment"}'
```

Reconcile a known pending provider refund with:

```powershell
docker compose exec web python manage.py reconcile_refund <refund-uuid>
```

Refunds do not delete or mutate the original settlement and do not reopen a `PAID` or `CLOSED`
parking session. If a refund-create response is lost before the provider refund ID is stored, locate
the operation in the Razorpay Dashboard using the refund UUID in `notes` before reconciling; blindly
reissuing it could duplicate money movement.

For a quote whose frozen amount is exactly zero, settle without creating an attempt or contacting a
provider:

```bash
curl -X POST http://localhost:8000/api/v1/parking-sessions/1/settle-zero/ \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{}'
```

After settlement the session is `PAID`, but its spot remains occupied. Only an ADMIN or OPERATOR can
record physical exit through an active `EXIT` or `BOTH` gate in the same lot:

```bash
curl -X POST http://localhost:8000/api/v1/parking-sessions/1/exit/ \
  -H "Authorization: Bearer <operator-access-token>" \
  -H "Content-Type: application/json" \
  -d '{"exit_gate_id":2}'
```

Exit locks session → gate → spot → quote → settlement → optional attempt, validates settlement,
records the immutable exit gate, actor, and timestamp, and changes `PAID` to `CLOSED` atomically.
Occupancy is derived from open session statuses, so no second occupied flag can drift. A disabled lot
or floor and a maintenance spot do not trap an already-paid vehicle; only the selected exit gate
must remain active and compatible.

### Reproducible local lifecycle demo

After setup, migrations, administrator creation, demo seeding, customer/vehicle creation, and token
acquisition, substitute the returned IDs in this sequence:

```bash
# 1. Observe initial capacity.
curl http://localhost:8000/api/v1/parking-lots/1/availability/ \
  -H "Authorization: Bearer <operator-access-token>"

# 2. Entry creates ACTIVE session and pricing snapshot.
curl -X POST http://localhost:8000/api/v1/parking-sessions/entry/ \
  -H "Authorization: Bearer <operator-access-token>" \
  -H "Content-Type: application/json" \
  -d '{"vehicle_id":1,"entry_gate_id":1}'

# 3. Checkout freezes quote and changes ACTIVE → PAYMENT_PENDING.
curl -X POST http://localhost:8000/api/v1/parking-sessions/1/checkout/ \
  -H "Authorization: Bearer <operator-access-token>" \
  -H "Content-Type: application/json" -d '{}'

# 4. Default SUCCESS simulator settles quote and changes PAYMENT_PENDING → PAID.
curl -X POST http://localhost:8000/api/v1/payments/ \
  -H "Authorization: Bearer <operator-access-token>" \
  -H "Content-Type: application/json" -d '{"parking_session_id":1}'

# 5. Exit changes PAID → CLOSED and releases derived occupancy.
curl -X POST http://localhost:8000/api/v1/parking-sessions/1/exit/ \
  -H "Authorization: Bearer <operator-access-token>" \
  -H "Content-Type: application/json" -d '{"exit_gate_id":2}'

# 6. Availability increases after CLOSED releases the spot.
curl http://localhost:8000/api/v1/parking-lots/1/availability/ \
  -H "Authorization: Bearer <operator-access-token>"
```

The migration adding exit attribution intentionally fails if historical `CLOSED` rows exist without
verified exit gate and actor data. Export and resolve those records using operational evidence before
retrying migration; the project never fabricates audit metadata. Full payment decisions, transaction
boundaries, ER and lifecycle diagrams are in
[ADR 0006](docs/decisions/0006-simulated-payments-settlement-and-exit.md). Simulator guarantees are
test/dev guarantees only and are not evidence of real-provider behavior or certification.
Razorpay-specific trust boundaries, failure handling, refunds, and webhook decisions are in
[ADR 0007](docs/decisions/0007-razorpay-payments-webhooks-and-refunds.md).

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

