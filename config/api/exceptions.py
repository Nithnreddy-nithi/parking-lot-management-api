from http import HTTPStatus

from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    default_detail = HTTPStatus(response.status_code).phrase

    if isinstance(exc, ValidationError):
        response.data = {
            "error": {
                "code": "validation_error",
                "detail": "Request validation failed.",
                "fields": data,
            }
        }
        return response

    if isinstance(data, dict) and "detail" in data:
        code = data.get("code", getattr(exc, "default_code", "api_error"))
        error = {"code": str(code), "detail": str(data["detail"])}
        extra = {key: value for key, value in data.items() if key not in {"code", "detail"}}
        if extra:
            error["fields"] = extra
        response.data = {"error": error}
    else:
        response.data = {
            "error": {
                "code": getattr(exc, "default_code", "api_error"),
                "detail": default_detail,
                "fields": data,
            }
        }
    return response
