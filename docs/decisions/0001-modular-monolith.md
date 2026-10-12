# ADR 0001: Start as a modular monolith

## Status

Accepted for Phase 1.

## Decision

The service is one Django deployment with business modules for accounts, parking inventory,
parking sessions, pricing, payments, reporting, and audit. Each module owns its models and future
application logic. The `apps.sessions` module uses the Django app label `parking_sessions`, avoiding
a collision with `django.contrib.sessions`. Other labels are also explicitly namespaced.

As functionality is introduced, HTTP views/controllers will handle transport, permissions, and
responses; serializers will validate request and response structure; application services will
coordinate use cases; domain policies will hold calculations and rules; selectors will express read
queries; repositories will exist only for meaningful persistence operations such as transactional
allocation with row locking; and adapters will isolate external systems. Django ORM access will not
be hidden behind a generic repository.

Later phases may justify Strategy implementations for allocation and pricing, payment Adapters, and
explicit state transitions for parking sessions. They are intentionally absent now. Likewise,
PostgreSQL constraints, `Decimal` money fields, transactions, locking, and consistent business-error
responses will be implemented alongside the business invariants they protect.

The custom `AbstractUser` model is created before the first migration because changing
`AUTH_USER_MODEL` after tables and foreign keys exist is disruptive. Keeping it minimal now provides
a safe extension point for later authentication or role requirements without prematurely designing
those features.

## Consequences

- Modules have clear ownership while sharing one database and deployment.
- Cross-module dependencies must remain explicit as use cases are added.
- No Redis, Celery, JWT endpoints, roles, parking logic, or external integrations are part of Phase 1.

