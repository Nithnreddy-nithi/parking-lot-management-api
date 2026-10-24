from django.core.management.base import BaseCommand, CommandError

from apps.payments.composition import build_payment_provider, build_payment_result_service
from apps.payments.exceptions import PaymentConflict, ProviderOutcomeUnknown, ProviderProtocolError
from apps.payments.models import PaymentAttempt


class Command(BaseCommand):
    help = "Retrieve and safely apply the configured provider result for one payment attempt."

    def add_arguments(self, parser):
        parser.add_argument("attempt_id")

    def handle(self, *args, **options):
        attempt_id = options["attempt_id"]
        try:
            attempt = PaymentAttempt.objects.get(pk=attempt_id)
        except (PaymentAttempt.DoesNotExist, ValueError) as exc:
            raise CommandError("Payment attempt not found.") from exc

        try:
            provider = build_payment_provider(attempt.provider)
            result = provider.retrieve_payment(
                merchant_reference=attempt.pk,
                provider_order_reference=attempt.provider_order_reference,
                provider_reference=attempt.provider_reference,
            )
            updated = build_payment_result_service().apply(
                attempt_id=attempt.pk,
                result=result,
            )
        except (ProviderOutcomeUnknown, ProviderProtocolError, PaymentConflict) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Payment {updated.pk} is {updated.status}."))
