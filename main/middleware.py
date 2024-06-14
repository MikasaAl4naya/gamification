from django.contrib.auth import logout
from django.http import JsonResponse


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