from functools import partial
from rest_framework.permissions import BasePermission

class HasPermission(BasePermission):
    def __init__(self, perm=None):
        """
        perm: Строка с конкретным разрешением, если оно требуется.
        """
        self.perm = perm

    def has_permission(self, request, view):
        # Если передано конкретное разрешение, проверяем его
        if self.perm:
            perm = self.perm
            print(f"Проверка конкретного разрешения для пользователя: {request.user.username}, Требуемое разрешение: {perm}")
            return request.user.has_perm(perm)

        # Если разрешение не указано, определяем действие исходя из метода запроса
        if hasattr(view, 'queryset'):
            model = view.queryset.model
        else:
            model = None

        # Определяем базовое действие для модели
        if model:
            action = self.get_action_based_on_method(request.method)
            perm = f"{model._meta.app_label}.{action}_{model._meta.model_name}"

            print(f"Проверка базового разрешения для пользователя: {request.user.username}, Требуемое разрешение: {perm}")
            return request.user.has_perm(perm)

        # Если не смогли определить модель или действие, отказываем в доступе
        return False

    def get_action_based_on_method(self, method):
        """
        Определяет действие в зависимости от метода HTTP-запроса.
        """
        if method in ['GET', 'HEAD', 'OPTIONS']:
            return 'view'
        elif method == 'POST':
            return 'add'
        elif method in ['PUT', 'PATCH']:
            return 'change'
        elif method == 'DELETE':
            return 'delete'
        return None



class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        print("Используется IsAdmin")
        is_authenticated = request.user.is_authenticated
        is_admin = request.user.groups.filter(name='Администраторы').exists()
        has_permission = is_authenticated and is_admin

        # Логируем информацию о пользователе и его роли
        user_info = {
            "username": request.user.username,
            "is_authenticated": is_authenticated,
            "is_admin": is_admin,
            "groups": list(request.user.groups.values_list('name', flat=True))
        }
        # print(f"User info: {user_info}")

        return has_permission

class IsModerator(BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name='Модераторы').exists()

class IsUser(BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name='Пользователи').exists()

class IsModeratorOrAdmin(BasePermission):
    def has_permission(self, request, view):
        is_authenticated = request.user.is_authenticated
        is_moderator = request.user.groups.filter(name='Модераторы').exists()
        is_admin = request.user.groups.filter(name='Администраторы').exists()
        has_permission = is_authenticated and (is_moderator or is_admin)

        # Логируем информацию о пользователе и его роли
        user_info = {
            "username": request.user.username,
            "is_authenticated": is_authenticated,
            "is_moderator": is_moderator,
            "is_admin": is_admin,
            "groups": list(request.user.groups.values_list('name', flat=True))
        }
        # print(f"User info: {user_info}")

        return has_permission
