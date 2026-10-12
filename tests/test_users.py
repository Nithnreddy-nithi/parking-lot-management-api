import pytest
from django.contrib.auth import get_user_model


@pytest.mark.django_db
def test_custom_user_persists_with_hashed_password():
    user_model = get_user_model()

    created_user = user_model.objects.create_user(
        username="operator",
        email="operator@example.com",
        password="a-secure-test-password",
    )

    persisted_user = user_model.objects.get(pk=created_user.pk)
    assert persisted_user.email == "operator@example.com"
    assert persisted_user.check_password("a-secure-test-password")
    assert persisted_user._meta.label == "parking_accounts.User"
