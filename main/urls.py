from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from . import views
from .views import *

urlpatterns = [
    path('achievements/', views.achievement_list, name='achievement_list'),
    path('achievements/create/', views.create_achievement, name='create_achievement'),
    path('create_request/', create_request, name='create_request'),
    path('success/', success_view, name='success'),
    path('register/', register, name='register_employee'),  # URL для страницы регистрации,
    path('login/', user_login, name='login'),
    path('registration_success/', registration_success, name='registration_success'),
    path('profile/', user_profile, name='user_profile'),
    path('logout/', logout_view, name='logout'),
    path('api/login/', LoginAPIView.as_view(), name='api-login'),
    path('employees/<str:username>/', EmployeeDetails.as_view(), name='employee_details'),
    path('api/register/', RegisterAPIView.as_view(), name='register'),
]
# Добавляем маршрут для обработки медиафайлов только в режиме отладки
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)