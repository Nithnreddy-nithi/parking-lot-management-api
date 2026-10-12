from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Project-owned user model, intentionally minimal for Phase 1."""
