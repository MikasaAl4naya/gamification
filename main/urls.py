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
    path('test/<int:test_id>/', views.test_detail, name='test_detail'),
    path('create_test/', create_test, name='create_test'),
    path('create_question/', CreateQuestion.as_view(), name='create_question'),
    path('create_answer/', CreateAnswer.as_view(), name='create_answer'),
    path('delete_test/<int:id>/', DeleteTest.as_view(), name='delete_test'),
    path('delete_question/<int:id>/', DeleteQuestion.as_view(), name='delete_question'),
    path('delete_answer/<int:id>/', DeleteAnswer.as_view(), name='delete_answer'),
    path('update_test/<int:id>/', UpdateTest.as_view(), name='update_test'),
    path('update_question/<int:id>/', UpdateQuestion.as_view(), name='update_question'),
    path('update_answer/<int:id>/', UpdateAnswer.as_view(), name='update_answer'),
    path('test_constructor/', test_constructor, name='test_constructor'),
    path('api/test/<int:test_id>/', views.get_test_by_id, name='get_test'),
    path('api/question/<int:question_id>/', views.get_question, name='get_question'),
    path('api/answer/<int:answer_id>/', views.get_answer, name='get_answer'),
    path('api/tests/', views.get_all_tests, name='get_all_tests'),
    path('api/create_acoin_transaction/', views.create_acoin_transaction, name='create_acoin_transaction'),
    path('users/', get_all_users, name='get_all_users'),
    path('user/<int:user_id>/', get_user, name='get_user'),
    path('user/<int:user_id>/balance/', get_user_balance, name='get_user_balance'),
    path('user/<int:user_id>/transactions/', get_user_transactions, name='get_user_transactions'),
]
# Добавляем маршрут для обработки медиафайлов только в режиме отладки
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)