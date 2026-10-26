from config.api.exceptions import Conflict


class PaymentConflict(Conflict):
    def __init__(self, *, code: str, detail: str):
        super().__init__({"code": code, "detail": detail})


class ProviderOutcomeUnknown(Exception):
    """The provider may have processed the request, but the caller received no result."""


class ProviderProtocolError(Exception):
    """A provider response violated the configured adapter contract."""
