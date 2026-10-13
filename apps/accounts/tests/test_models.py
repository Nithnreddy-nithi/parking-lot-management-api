import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import User


@pytest.mark.django_db
def test_database_rejects_unknown_application_role():
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(username="invalid-role", role="UNKNOWN")
