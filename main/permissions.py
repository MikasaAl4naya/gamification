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

class IsSelfOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (request.user.id == view.kwargs['user_id'] or request.user.groups.filter(name='Администраторы').exists())
