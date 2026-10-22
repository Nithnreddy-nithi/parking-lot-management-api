from rest_framework.exceptions import NotFound

from config.api.exceptions import Conflict


class PricingConflict(Conflict):
    def __init__(self, *, code: str, detail: str):
        super().__init__({"code": code, "detail": detail})


class QuoteNotFound(NotFound):
    def __init__(self):
        super().__init__({"code": "QUOTE_NOT_FOUND", "detail": "Checkout quote not found."})
