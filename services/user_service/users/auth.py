from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.conf import settings
import jwt

class VerifyTokenView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith("Bearer "):
            return Response({"valid": False, "reason": "Invalid auth header"}, status=401)

        token = auth_header.replace("Bearer ", "")
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            return Response({
                "valid": True,
                "user_id": payload.get("sub"),
                "role": payload.get("role", "user"),
            })
        except jwt.ExpiredSignatureError:
            return Response({"valid": False, "reason": "Token expired"}, status=401)
        except jwt.InvalidTokenError:
            return Response({"valid": False, "reason": "Invalid token"}, status=401)
