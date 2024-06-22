# views_base.py

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.response import Response


class EmployeeAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        token_key = request.auth.key
        try:
            token = Token.objects.get(key=token_key)
            request.employee = token.user
        except Token.DoesNotExist:
            self.permission_denied(request, message="Invalid token")
        except AttributeError:
            self.permission_denied(request, message="Employee not found for this token")