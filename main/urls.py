# urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views
from .serializers import GroupViewSet, PermissionViewSet
from .views import *

router = DefaultRouter()
router.register(r'groups', GroupViewSet)
router.register(r'permissions', PermissionManagementViewSet,basename='permission-management')
router.register(r'players', PlayersViewSet)
router.register(r'survey-questions', SurveyQuestionViewSet)
router.register(r'survey-answers', SurveyAnswerViewSet)
router.register(r'classifications', ClassificationsViewSet)
router.register(r'currency-logs', EmployeeLogViewSet)
router.register(r'karma-settings', KarmaSettingsViewSet)
router.register(r'file-paths', FilePathViewSet)
router.register(r'experience-multipliers', ExperienceMultiplierViewSet)
router.register(r'system-settings', SystemSettingViewSet, basename='system-setting')
router.register(r'level-titles', LevelTitleViewSet, basename='level-titles')
router.register(r'password-policy', PasswordPolicyViewSet, basename='password_policy_regex')
router.register(r'logs', EmployeeActionLogViewSet, basename='logs')
router.register(r'preloaded-avatars', PreloadedAvatarUploadViewSet, basename='preloaded-avatars')
router.register(r'achievements', AchievementViewSet, basename='achievement')

urlpatterns = [
    # Включение маршрутов, зарегистрированных с помощью DefaultRouter
    path('', include(router.urls)),
    path('login/', LoginAPIView.as_view(), name='api-login'),
    path('employee/<str:username>/', EmployeeDetails.as_view(), name='employee-details'),
    path('register/', RegisterAPIView.as_view(), name='register'),
    path('create_test/', create_test, name='create_test'),
    path('create_question/', CreateQuestion.as_view(), name='create_question'),
    path('create_answer/', CreateAnswer.as_view(), name='create_answer'),
    path('delete_test/<int:id>/', DeleteTest.as_view(), name='delete_test'),
    path('delete_question/<int:id>/', DeleteQuestion.as_view(), name='delete_question'),
    path('delete_answer/<int:id>/', DeleteAnswer.as_view(), name='delete_answer'),
    path('update_test/<int:id>/', UpdateTest.as_view(), name='update_test'),
    path('update_question/<int:id>/', UpdateQuestion.as_view(), name='update_question'),
    path('update_answer/<int:id>/', UpdateAnswer.as_view(), name='update_answer'),
    path('test/<int:test_id>/', views.get_test_by_id, name='get_test'),
    path('question/<int:question_id>/', views.get_question, name='get_question'),
    path('answer/<int:answer_id>/', views.get_answer, name='get_answer'),
    path('tests/', views.get_all_tests, name='get_all_tests'),
    path('create_acoin_transaction/', views.create_acoin_transaction, name='create_acoin_transaction'),
    path('users/', get_all_users, name='get_all_users'),
    path('user/<int:user_id>/balance/', get_user_balance, name='get_user_balance'),
    path('user/<int:user_id>/transactions/', get_user_transactions, name='get_user_transactions'),
    path('answer_options/<int:pk>/', AnswerOptionDetailView.as_view(), name='answer_option_detail'),
    path('questions/<int:question_id>/', TestQuestionDetail.as_view()),
    path('theories/', TheoryList.as_view(), name='theory-list'),
    path('theories/create/', TheoryCreate.as_view(), name='theory-create'),
    path('theories/<int:id>/', TheoryDetail.as_view(), name='theory-detail'),
    path('themes-with-tests/', ThemesWithTestsView.as_view(), name='themes-with-tests'),
    path('achievements/create/', views.create_achievement, name='create_achievement'),
    path('requests/create/', create_request, name='create_request'),
    path('complete_test/<int:employee_id>/<int:test_id>/', CompleteTestView.as_view(), name='complete_test'),
    path('start_test_attempt/<int:test_id>/<int:employee_id>/', start_test_attempt, name='start_test_attempt'),
    path('get_test_with_theory/<test_id>/', get_test_with_theory, name='get_test_with_theory'),
    path('create_theme/', create_theme, name='create_theme'),
    path('themes/', theme_list, name='theme_list'),
    path('delete_all_tests/', delete_all_tests, name='delete_all_tests'),
    path('tests/<int:test_id>/questions_with_explanations/', get_questions_with_explanations, name='questions_with_explanations'),
    path('classifications/create/', CreateClassificationAPIView.as_view(), name='create_classification'),
    path('test_attempts/', list_test_attempts, name='list_test_attempts'),
    path('test_attempts/<int:attempt_id>/', get_test_attempt, name='get_test_attempt'),
    path('test_attempts/moderation/', test_attempt_moderation_list, name='test_attempt_moderation_list'),
    path('test_attempts/<int:test_attempt_id>/moderate/', moderate_test_attempt, name='moderate_test_attempt'),
    path('test_attempts/<int:employee_id>/<int:test_id>/reattempt_delay/', reattempt_delay, name='reattempt_delay'),
    path('start_test/<int:employee_id>/<int:test_id>/', StartTestView.as_view(), name='start_test'),
    path('attempts/delete_all', delete_all_test_attempts, name='delete-all-attempts'),
    path('attempts/delete/<int:attempt_id>/', delete_test_attempt, name='delete-attempt'),
    path('review-test-attempts/', review_test_attempts, name='review_test_attempts'),
    path('test_attempt/test_results/<int:test_attempt_id>', test_results, name='test_results'),
    path('update_test_and_content/<int:test_id>/', UpdateTestAndContent.as_view(), name='update_test_and_content'),
    path('employees/<int:employee_id>/tests/<int:test_id>/status/', test_status),
    path('tests/required_tests_chain/<int:employee_id>/<int:test_id>/', required_tests_chain, name='required_tests'),
    path('test_duration/<int:test_id>/', get_test_duration, name='get_test_duration'),
    path('test-score/<int:test_id>/', TestScoreAPIView.as_view(), name='test-score'),
    path('employee-stats/', StatisticsAPIView.as_view(), name='employee_stats'),
    path('test-time-stat/', TestStatisticsAPIView.as_view(), name='test-time-stat'),
    path('full_statistics/', FullStatisticsAPIView.as_view(), name='full_statistics'),
    path('test_moderation_result/<int:test_attempt_id>/', test_moderation_result, name='test_moderation_result'),
    path('themes/<int:theme_id>/delete', ThemeDeleteAPIView.as_view(), name='theme_delete'),
    path('themes/<int:theme_id>/update-name/', update_theme_name, name='update_theme_name'),
    path('test-attempts/<int:attempt_id>/delete/', delete_test_attempt, name='delete_test_attempt'),
    path('question_errors_stat/', QuestionErrorsStatistics.as_view(), name='emp_test_stat'),
    path('question_correct_stat/', QuestionCorrectStatistics.as_view(), name='emp_test_stat'),
    path('test-stat/', get_test_statistics, name='get_statistics'),
    path('user/update/', EmployeeUpdateView.as_view(), name='employee-update'),
    # path('test/<int:test_id>/top_participants/', top_test_participants, name='top_test_participants'),
    path('top_participants/', top_participants, name='top_participants'),
    path('delete_user/<int:user_id>/', delete_user, name='delete_user'),
    path('employee/update/<int:pk>/', AdminEmployeeUpdateView.as_view(), name='admin-employee-update'),
    path('users/<int:user_id>/deactivate/', deactivate_user, name='deactivate_user'),
    path('users/<int:user_id>/delete/', delete_user, name='delete_user'),
    path('users/<int:user_id>/activate/', activate_user, name='activate_user'),
    path('set_file_path/', set_file_path, name='set_file_path'),
    path('employee/<int:employee_id>/achievements/', EmployeeAchievementsView.as_view(), name='employee-achievements'),
    path('get_karma_history/<int:employee_id>/', get_karma_history, name='get_karma_history'),
    path('positions/', PositionListView.as_view(), name='position-list'),
    path('reset_karma/', reset_karma, name='reset_karma'),
    path('reset_karma/<int:employee_id>/', reset_karma, name='reset_karma_employee'),
    path('delete-all-classifications/', DeleteAllClassificationsView.as_view(), name='delete-all-classifications'),
    path('update_status/', UpdateStatusView.as_view(), name='update_status'),
    path('update_profile/', UpdateProfileView.as_view(), name='update_profile'),
    path('get_user/', get_user, name='get_user'),
    path('create_feedback/<str:type>/<int:employee_id>/', views.create_feedback, name='create_feedback'),
    path('moderate_feedback/<int:feedback_id>/', views.moderate_feedback, name='moderate_feedback'),
    path('feedbacks/pending/', feedbacks_pending_moderation, name='feedbacks_pending_moderation'),
    path('system-statistics/', system_statistics, name='file-system_statistics'),
    path('sessions/', SessionListView.as_view(), name='session-list'),
    path('admin-change-password/<int:user_id>/', PasswordManagementView.as_view(), name='admin_change_password'),
    path('password-change/', PasswordManagementView.as_view(), name='user_change_password'),
    path('survey/questions/', SurveyQuestionView.as_view(), name='survey-questions'),
    path('survey/answers/', submit_survey_answers, name='user_change_password'),
    path('feedback/<int:pk>/', FeedbackDetailView.as_view(), name='feedback-detail'),
    path('upload-and-analyze/', FileUploadAndAnalysisView.as_view(), name='upload-and-analyze'),
    path('select-avatar/', select_avatar, name='change-avatar'),
    path('micro-profile/', get_micro_user, name='micro-profile'),
    path('update-karma-settings/', KarmaSettingsUpdateView.as_view(), name='update_karma_settings'),
    path('late-penalty-settings/', get_late_penalty_settings, name='get_late_penalty_settings'),
    path('update-late-penalty-settings/', update_late_penalty_settings, name='update_late_penalty_settings'),
    path('store/', StoreView.as_view(), name='store'),
    path('assign-achievement/', assign_achievement, name='assign_achievement'),
    path('get_complaints/<int:employee_id>/', get_employee_complaints, name='get_employee_complaints'),
]
# Добавляем маршрут для обработки медиафайлов только в режиме отладки
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
