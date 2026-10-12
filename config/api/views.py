from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from config.api.serializers import HealthResponseSerializer


@extend_schema(responses=HealthResponseSerializer)
@api_view(["GET"])
@permission_classes([AllowAny])
def live_health(request: Request) -> Response:
    return Response({"status": "ok"})
