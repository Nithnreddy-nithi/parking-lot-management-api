from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create an application ADMIN without granting Django staff or superuser flags."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", default="")

    def handle(self, *args, **options):
        user_model = get_user_model()
        username = options["username"]
        if user_model.objects.filter(username=username).exists():
            raise CommandError(f"User {username!r} already exists")

        password = getpass("Password: ")
        confirmation = getpass("Password (again): ")
        if password != confirmation:
            raise CommandError("Passwords do not match")

        candidate = user_model(
            username=username, email=options["email"], role=user_model.Role.ADMIN
        )
        try:
            validate_password(password, user=candidate)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc

        candidate.set_password(password)
        candidate.save()
        self.stdout.write(
            self.style.SUCCESS(
                f"Created application ADMIN {username!r} (is_staff=False, is_superuser=False)"
            )
        )
