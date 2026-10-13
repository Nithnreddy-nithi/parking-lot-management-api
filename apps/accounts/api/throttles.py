from rest_framework.throttling import ScopedRateThrottle


class RegistrationThrottle(ScopedRateThrottle):
    scope = "auth_register"


class TokenThrottle(ScopedRateThrottle):
    scope = "auth_token"
