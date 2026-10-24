from django.core.management.base import BaseCommand, CommandError

from apps.payments.composition import build_payment_provider, build_refund_result_service
from apps.payments.exceptions import PaymentConflict, ProviderOutcomeUnknown, ProviderProtocolError
from apps.payments.models import Refund


class Command(BaseCommand):
    help = "Retrieve and safely apply the provider result for one refund."

    def add_arguments(self, parser):
        parser.add_argument("refund_id")

    def handle(self, *args, **options):
        try:
            refund = Refund.objects.select_related("settlement__payment_attempt").get(
                pk=options["refund_id"]
            )
        except (Refund.DoesNotExist, ValueError) as exc:
            raise CommandError("Refund not found.") from exc
        if not refund.provider_reference:
            raise CommandError(
                "The provider refund reference is unknown; locate it in Razorpay Dashboard first."
            )
        attempt = refund.settlement.payment_attempt
        try:
            provider = build_payment_provider(attempt.provider)
            result = provider.retrieve_refund(
                merchant_reference=refund.pk,
                provider_reference=refund.provider_reference,
            )
            updated = build_refund_result_service().apply(refund_id=refund.pk, result=result)
        except (ProviderOutcomeUnknown, ProviderProtocolError, PaymentConflict) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Refund {updated.pk} is {updated.status}."))
