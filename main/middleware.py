import logging

from django.contrib.auth import logout
from rest_framework.authtoken.models import Token
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from main.models import Employee, UserSession, SystemSetting


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

from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

class UpdateLastLoginMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.user.is_authenticated:
            # Обновляем поле last_login для пользователя
            Employee.objects.filter(id=request.user.id).update(last_login=timezone.now())

class EmployeeMiddleware(MiddlewareMixin):
    def process_request(self, request):
        token_key = request.META.get('HTTP_AUTHORIZATION')
        if token_key and token_key.startswith('Token '):
            try:
                token_key = token_key.split(' ')[1]
                token = Token.objects.get(key=token_key)
                request.employee = token.user
                # Обновляем поле last_login при использовании токена
                Employee.objects.filter(id=token.user.id).update(last_login=timezone.now())
            except Token.DoesNotExist:
                return JsonResponse({"message": "Invalid token"}, status=403)
        else:
            request.employee = None
class UpdateLastActivityMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.user.is_authenticated:
            request.user.last_activity = timezone.now()
            request.user.save()
class ActiveSessionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.user.is_authenticated:
            session_key = request.session.session_key
            user_sessions = UserSession.objects.filter(user=request.user)
            max_active_sessions= SystemSetting.objects.get(key='max_active_sessions')
            # Проверка максимального количества активных сессий
            if user_sessions.count() >= int(max_active_sessions.value):
                # Завершаем самую старую сессию
                oldest_session = user_sessions.order_by('created_at').first()
                oldest_session.session.delete()
                oldest_session.delete()

            # Обновляем или создаем новую запись для сессии
            user_session, created = UserSession.objects.get_or_create(user=request.user, session_id=session_key)
            user_session.last_activity = timezone.now()
            user_session.ip_address = request.META.get('REMOTE_ADDR')
            user_session.user_agent = request.META.get('HTTP_USER_AGENT')
            user_session.save()

        # Очищаем старые сессии, если они не обновлялись длительное время
        UserSession.objects.filter(last_activity__lt=timezone.now() - timezone.timedelta(hours=1)).delete()