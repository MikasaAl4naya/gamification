import logging

from django.contrib.auth import logout
from rest_framework.authtoken.models import Token
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

class CheckActiveUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Если пользователь не аутентифицирован, пропускаем
        if not request.user.is_authenticated:
            return self.get_response(request)

        # Проверяем активен ли пользователь
        if hasattr(request.user, 'is_active') and not request.user.is_active:
            # Осуществляем logout деактивированного пользователя
            logout(request)
            return JsonResponse({"message": "Account is deactivated"}, status=403)

        return self.get_response(request)

class EmployeeMiddleware(MiddlewareMixin):
    def process_request(self, request):
        token_key = request.META.get('HTTP_AUTHORIZATION')
        if token_key and token_key.startswith('Token '):
            try:
                token_key = token_key.split(' ')[1]
                token = Token.objects.get(key=token_key)
                request.employee = token.user
            except Token.DoesNotExist:
                return JsonResponse({"message": "Invalid token"}, status=403)
        else:
            request.employee = None