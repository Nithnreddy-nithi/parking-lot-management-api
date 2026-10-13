# Phase 2 PR description

## Problem

The foundation has no way for customers to register or authenticate, and no business-role boundary
for future parking operations and administration.

## Change

- Extend the custom user with constrained ADMIN, OPERATOR, and CUSTOMER roles plus audit timestamps.
- Add Simple JWT login, refresh rotation/blacklisting, owned-token logout, profile updates, and
  password changes with refresh-token revocation.
- Add ADMIN-only paginated/filterable user management while protecting ADMIN/superuser records and
  Django privilege flags.
- Add consistent API errors, OpenAPI descriptions, authentication throttles, an application-ADMIN
  bootstrap command, and Phase 2 usage documentation.
- Keep role permissions, selectors, serializers, views, and write services in explicit layers.

## Validation

- `ruff check .`
- `ruff format --check .`
- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `pytest`
- `docker build --target runtime -t parking-lot-api:phase2 .`

## Migrations

- Add `role`, `created_at`, and `updated_at` to the custom user.
- Backfill existing users as CUSTOMER and apply a database constraint for valid role values.
- Apply Simple JWT blacklist migrations.

Run `python manage.py migrate` as a separate deployment step before serving the new application.

## Risks

- Logout and password changes cannot revoke already-issued stateless access tokens; they remain valid
  until the configured short expiration.
- DRF throttling is application-level; production needs infrastructure rate limiting and a shared
  cache when running multiple processes.
- Existing users receive the CUSTOMER role and should be reviewed if environments already contain
  manually created operational accounts.

