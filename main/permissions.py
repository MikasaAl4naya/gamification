from rest_framework.permissions import BasePermission


class HasPermission(BasePermission):
    def __init__(self, perm=None):
        self.perm = perm

    def has_permission(self, request, view):
        if self.perm:
            perm = self.perm
        else:
            # Определяем модель из queryset и действие
            model = view.queryset.model
            action = 'view' if request.method in ['GET', 'HEAD', 'OPTIONS'] else \
                     'add' if request.method == 'POST' else \
                     'change' if request.method in ['PUT', 'PATCH'] else \
                     'delete'
            # Определяем полное имя разрешения
            perm = f"{model._meta.app_label}.{action}_{model._meta.model_name}"

        print(f"Проверка разрешений для пользователя: {request.user.username}")
        print(f"Требуемое разрешение: {perm}")
        return request.user.has_perm(perm)



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
