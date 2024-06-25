from rest_framework.permissions import BasePermission

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name='Администраторы').exists()

class IsModerator(BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name='Модераторы').exists()

class IsUser(BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name='Пользователи').exists()

class IsModeratorOrAdmin(BasePermission):
    def has_permission(self, request, view):
        is_authenticated = request.user.is_authenticated
        is_moderator = request.user.groups.filter(name='moderator').exists()
        is_admin = request.user.groups.filter(name='Администраторы').exists()  # Изменено на русское название группы
        has_permission = is_authenticated and (is_moderator or is_admin)

        # Логируем информацию о пользователе и его роли
        user_info = {
            "username": request.user.username,
            "is_authenticated": is_authenticated,
            "is_moderator": is_moderator,
            "is_admin": is_admin,
            "groups": list(request.user.groups.values_list('name', flat=True))
        }
        print(f"User info: {user_info}")

        return has_permission

