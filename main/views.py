import base64
import math
import time

from django.db.models import F, ExpressionWrapper, IntegerField, CharField, Value, BooleanField
import uuid
from collections import Counter, defaultdict
from datetime import timedelta, datetime
from decimal import Decimal, ROUND_HALF_UP
from functools import partial
from django.contrib.auth.hashers import make_password, check_password
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.views.decorators.http import require_POST
from .permissions import IsAdmin, IsModerator, IsUser, IsModeratorOrAdmin, HasPermission
from django.views.decorators.csrf import csrf_exempt
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
import pytz
from django.db.models import Max, FloatField, Avg, Count, Q, F, Sum, ExpressionWrapper, DurationField, OuterRef, \
    Subquery, Window, When, Case
from django.db.models.functions import Coalesce, RowNumber, Concat
from django.http import HttpResponse, JsonResponse
from django.utils.timezone import localtime
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import  BasePermission, IsAuthenticated, AllowAny
from rest_framework.utils import json
from json.decoder import JSONDecodeError
from .models import *
from rest_framework.generics import get_object_or_404
from rest_framework.decorators import api_view, parser_classes, permission_classes, authentication_classes, action
from .serializers import *
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics, viewsets
from django.contrib.auth import authenticate
from .views_base import EmployeeAPIView
class BasePermissionViewSet(viewsets.ModelViewSet):
    """
    Базовый класс для ViewSet, который автоматически проверяет права на основе модели и действия.
    """
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'update', 'destroy', 'list', 'retrieve']:
            # Проверка на None
            if self.queryset is not None:
                model = self.queryset.model
                action = {
                    'create': 'add',
                    'update': 'change',
                    'partial_update': 'change',
                    'destroy': 'delete',
                    'list': 'view',
                    'retrieve': 'view',
                }[self.action]
                perm = f"{model._meta.app_label}.{action}_{model._meta.model_name}"
                self.permission_classes = [IsAuthenticated, partial(HasPermission, perm=perm)]

        if hasattr(self, 'extra_permission_classes') and self.action in self.extra_permission_classes:
            self.permission_classes = [IsAuthenticated] + self.extra_permission_classes[self.action]

        return super().get_permissions()

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_logs(request):
    # Получаем параметры из запроса
    employee_id = request.query_params.get('employee_id', None)
    log_type = request.query_params.get('log_type', 'both')  # Значение по умолчанию - удалить оба типа логов

    # Если employee_id не передан, будем удалять логи по всем сотрудникам
    if employee_id:
        employee = get_object_or_404(Employee, id=employee_id)
    else:
        employee = None

    # Инициализируем счётчики удалённых логов
    employee_logs_deleted = 0
    employee_action_logs_deleted = 0

    # Логика для удаления логов в зависимости от переданного типа
    if log_type in ['both', 'employee_log']:
        if employee:
            # Удаляем логи из EmployeeLog для конкретного сотрудника
            employee_logs_deleted, _ = EmployeeLog.objects.filter(employee=employee).delete()
        else:
            # Удаляем все логи из EmployeeLog
            employee_logs_deleted, _ = EmployeeLog.objects.all().delete()

    if log_type in ['both', 'employee_action_log']:
        if employee:
            # Удаляем логи из EmployeeActionLog для конкретного сотрудника
            employee_action_logs_deleted, _ = EmployeeActionLog.objects.filter(employee=employee).delete()
        else:
            # Удаляем все логи из EmployeeActionLog
            employee_action_logs_deleted, _ = EmployeeActionLog.objects.all().delete()

    return Response({
        "message": f"Deleted {employee_logs_deleted} logs from EmployeeLog and {employee_action_logs_deleted} logs from EmployeeActionLog"
    }, status=status.HTTP_200_OK)

class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    @csrf_exempt
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data.get('username')
            password = serializer.validated_data.get('password')

            user = authenticate(request, username=username, password=password)
            if user is not None:
                # Получаем токен пользователя
                token, created = Token.objects.get_or_create(user=user)

                employee = Employee.objects.get(username=username)
                experience = employee.experience
                karma = employee.karma
                acoin = Acoin.objects.get(employee=employee).amount
                first_name = employee.first_name
                last_name = employee.last_name

                # Получаем группы пользователя
                groups = user.groups.values_list('name', flat=True)

                # Возвращаем успешный ответ с данными сотрудника и токеном
                return Response({
                    'message': 'Login successful',
                    'employee_id': employee.id,
                    'experience': experience,
                    'karma': karma,
                    'acoin': acoin,
                    'groups': list(groups),
                    'token': token.key,
                    'first_name': first_name,
                    'last_name': last_name
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'message': 'Invalid username or password',
                    'data': serializer.validated_data
                }, status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




class DeleteAllClassificationsView(APIView):
    def delete(self, request, *args, **kwargs):
        Classifications.objects.all().delete()
        return Response({"message": "All classifications have been deleted."}, status=status.HTTP_204_NO_CONTENT)

@permission_classes([IsAdmin])
class TestScoreAPIView(APIView):
    def get(self, request, test_id):
        # Получаем максимальное количество баллов и количество попыток для каждого сотрудника
        max_scores = TestAttempt.objects.filter(test_id=test_id).values('employee_id').annotate(
            max_score=Coalesce(Max('score'), 0, output_field=FloatField()),
            attempts=Count('id')
        )

        # Вычисляем средний балл теста по всем участникам
        average_score = TestAttempt.objects.filter(test_id=test_id).aggregate(avg_score=Avg('score'))['avg_score'] or 0

        # Формируем список с результатами для каждого сотрудника
        scores = [{'employee_id': item['employee_id'], 'max_score': item['max_score'], 'attempts': item['attempts']} for item in max_scores]

        # Добавляем средний балл теста к результатам
        result = {
            'average_score': average_score,
            'individual_scores': scores
        }
        return Response(result)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
def deactivate_user(request, user_id):
    try:
        employee = Employee.objects.get(id=user_id)
        employee.deactivate()
        return Response({"message": "User deactivated successfully"}, status=status.HTTP_200_OK)
    except Employee.DoesNotExist:
        return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    except ValidationError as e:
        return Response({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        # Логирование ошибки для отладки
        return Response({"message": f"Unexpected error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAdmin])
def delete_user(request, user_id):
    try:
        employee = Employee.objects.get(id=user_id)
        employee.delete_employee()
        return Response({"message": "User deleted successfully"}, status=status.HTTP_200_OK)
    except Employee.DoesNotExist:
        return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    except ValidationError as e:
        return Response({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAdmin])
def activate_user(request, user_id):
    try:
        employee = Employee.objects.get(id=user_id)
        employee.activate()
        return Response({"message": "User activated successfully"}, status=status.HTTP_200_OK)
    except Employee.DoesNotExist:
        return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    except ValidationError as e:
        return Response({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)
@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAdmin])
def test_statistics(request):
    attempts_with_statistics = TestAttempt.objects.annotate(
        duration=ExpressionWrapper(
            F('end_time') - F('start_time'),
            output_field=DurationField()
        ),
        score_percentage=ExpressionWrapper(
            F('score') * 100 / F('test__max_score'),
            output_field=FloatField()
        )
    ).select_related('employee', 'test', 'test__theme')

    last_attempts = {}
    for attempt in attempts_with_statistics:
        if attempt.end_time is not None:
            key = (attempt.employee.id, attempt.test.id)
            if key not in last_attempts or attempt.end_time > last_attempts[key].end_time:
                last_attempts[key] = attempt

    statistics = []
    all_tests = set()
    all_themes = set()
    all_employees = set()

    for attempt in attempts_with_statistics:
        employee_name = f"{attempt.employee.first_name} {attempt.employee.last_name}"
        theme_name = attempt.test.theme.name
        test_name = attempt.test.name
        score = attempt.score
        max_score = attempt.test.max_score

        test_results = attempt.test_results
        moderator_name = None
        if test_results:
            try:
                test_results_data = json.loads(test_results)
                moderator_name = test_results_data.get("moderator")
            except (TypeError, JSONDecodeError):
                pass

        duration_seconds = round(attempt.duration.total_seconds(), 0) if attempt.end_time else None
        if duration_seconds is not None:
            duration_minutes = int(duration_seconds // 60)
        else:
            duration_minutes = None
        end_time = attempt.end_time.strftime("%Y-%m-%d %H:%M") if attempt.end_time else None
        duration_seconds = int(duration_seconds % 60) if duration_seconds is not None else None
        duration = f"{duration_minutes}:{duration_seconds:02}" if duration_minutes is not None and duration_seconds is not None else None
        test_status = attempt.status
        test_acoin_reward = attempt.test.acoin_reward
        test_experience_points = attempt.test.experience_points
        test_id = attempt.test.id if attempt.test is not None else None
        is_last_attempt = last_attempts.get((attempt.employee.id, attempt.test.id)) == attempt

        statistics.append({
            'employee_name': employee_name,
            'theme_name': theme_name,
            'test_id': test_id,
            'test_name': test_name,
            'score': score,
            'test_attempt': attempt.id,
            'max_score': max_score,
            'duration': duration,
            'end_time': end_time,
            'moderator': moderator_name,
            'status': test_status,
            'test_acoin_reward': test_acoin_reward,
            'test_experience_points': test_experience_points,
            'is_last_attempt': is_last_attempt

        })

        all_tests.add((test_id, test_name))
        all_themes.add(theme_name)
        all_employees.add(employee_name)

    sorted_statistics = sorted(statistics, key=lambda x: (x['employee_name'], x['theme_name']))
    sorted_tests = sorted(list(all_tests), key=lambda x: x[1])
    sorted_themes = sorted(list(all_themes))
    sorted_employees = sorted(list(all_employees))

    result = {
        'statistics': sorted_statistics,
        'tests': [{'test_id': test_id, 'test_name': test_name} for test_id, test_name in sorted_tests],
        'themes': sorted_themes,
        'employees': sorted_employees
    }

    return Response(result)
@authentication_classes([TokenAuthentication])
@permission_classes([IsAdmin])
class MostIncorrectQuestionsAPIView(APIView):
    def get(self, request):
        # Получаем список вопросов, по которым сотрудники чаще всего ошибаются
        most_incorrect_questions = TestQuestion.objects.annotate(
            incorrect_count=Count('testattemptquestionexplanation', filter=~Q(testattemptquestionexplanation__is_correct=True))
        ).order_by('-incorrect_count')[:10]

        # Формируем список вопросов и количества ошибок для каждого вопроса
        result = [{'question_text': question.text, 'incorrect_count': question.incorrect_count} for question in most_incorrect_questions]

        return Response(result)

@api_view(['GET'])
def get_employee_info(request, employee_id):
    try:
        employee = Employee.objects.get(id=employee_id)
        if not employee.is_active:
            return Response({"message": "Account is deactivated"}, status=status.HTTP_403_FORBIDDEN)
    except Employee.DoesNotExist:
        return Response({"message": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = EmployeeSerializer(employee)
    return Response(serializer.data, status=status.HTTP_200_OK)
class TemplateViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Template.objects.all()
    serializer_class = TemplateSerializer
class EmployeeAchievementsView(generics.ListAPIView):
    serializer_class = AchievementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        employee_id = self.kwargs['employee_id']
        employee_achievements = EmployeeAchievement.objects.filter(employee_id=employee_id)
        achievement_ids = employee_achievements.values_list('achievement_id', flat=True)
        return Achievement.objects.filter(id__in=achievement_ids)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        employee_achievements = EmployeeAchievement.objects.filter(employee_id=self.kwargs['employee_id'])
        achievement_data = []

        for achievement in queryset:
            employee_achievement = employee_achievements.get(achievement=achievement)
            achievement_data.append({
                'id': achievement.id,
                'name': achievement.name,
                'description': achievement.description,
                'type': achievement.type,
                'required_count': achievement.required_count,
                'reward_experience': achievement.reward_experience,
                'reward_currency': achievement.reward_currency,
                'image': achievement.image.url,
                'max_level': achievement.max_level,
                'progress': employee_achievement.progress,
                'level': employee_achievement.level
            })

        return Response(achievement_data)
class DynamicPermission(BasePermission):
    def has_permission(self, request, view):
        required_permission = view.required_permissions.get(request.method.lower())
        if required_permission:
            has_perm = request.user.has_perm(required_permission)
            return has_perm
        return False

@api_view(['POST'])
@permission_classes([IsAdmin])  # Только администратор может присваивать достижения
def assign_achievement(request):
    employee_id = request.data.get('employee_id')
    achievement_id = request.data.get('achievement_id')

    try:
        employee = Employee.objects.get(id=employee_id)
        achievement = Achievement.objects.get(id=achievement_id)
    except Employee.DoesNotExist:
        return Response({"error": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)
    except Achievement.DoesNotExist:
        return Response({"error": "Achievement not found"}, status=status.HTTP_404_NOT_FOUND)

    # Проверка, если достижение можно получить только один раз и уже было присвоено
    if  EmployeeAchievement.objects.filter(employee=employee, achievement=achievement).exists():
        return Response({"message": "This achievement can only be earned once and has already been assigned."},
                        status=status.HTTP_400_BAD_REQUEST)

    # Присвоение достижения
    employee_achievement = EmployeeAchievement.objects.create(
        employee=employee,
        achievement=achievement,
        assigned_manually=True
    )
    employee_achievement.reward_employee()

    return Response({"message": "Achievement assigned successfully"}, status=status.HTTP_200_OK)


class AchievementViewSet(viewsets.ModelViewSet):
    queryset = Achievement.objects.all()
    serializer_class = AchievementSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def perform_create(self, serializer):
        achievement = serializer.save()
        if achievement.is_award:
            print(f"A unique award has been created: {achievement.name}")
        else:
            print(f"A standard achievement has been created: {achievement.name}")

    def perform_update(self, serializer):
        achievement = serializer.save()
        if achievement.is_award:
            print(f"A unique award has been updated: {achievement.name}")
        else:
            print(f"An achievement has been updated: {achievement.name}")
class UpdateStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, *args, **kwargs):
        # Получаем ID пользователя из параметров запроса, если он указан
        employee_id = request.data.get('id', None)

        # Если указан id, проверяем, является ли текущий пользователь администратором
        if employee_id:
            if not request.user.is_staff:  # Проверяем, является ли пользователь администратором
                return Response({"detail": "У вас нет прав для изменения статуса этого пользователя."},
                                status=status.HTTP_403_FORBIDDEN)

            # Получаем сотрудника по указанному ID
            employee = get_object_or_404(Employee, id=employee_id)
        else:
            # Если ID не указан, значит пользователь хочет изменить статус себе
            employee = request.user

        # Используем сериализатор для обновления статуса
        serializer = StatusUpdateSerializer(employee, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class UpdateProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, *args, **kwargs):
        serializer = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class EmployeeUpdateView(generics.UpdateAPIView):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def put(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)
class AdminEmployeeUpdateView(generics.UpdateAPIView):
    queryset = Employee.objects.all()
    serializer_class = AdminEmployeeSerializer
    permission_classes = [IsAdmin]

    def put(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.put(request, *args, **kwargs)
class EmployeeDetails(APIView):
    def get(self, request, username):
        try:
            employee = Employee.objects.get(username=username)
            serializer = EmployeeSerializer(employee)
            return Response(serializer.data)
        except Employee.DoesNotExist:
            return Response({"message": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)

    def patch(self, request, username):
        try:
            employee = Employee.objects.get(username=username)
            serializer = EmployeeSerializer(employee, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Employee.DoesNotExist:
            return Response({"message": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)
@authentication_classes([TokenAuthentication])
class RegisterAPIView(APIView):
    @transaction.atomic
    def post(self, request):
        serializer = EmployeeRegSerializer(data=request.data)
        if serializer.is_valid():
            employee = serializer.save()

            password = get_random_string(length=10)
            employee.set_password(password)
            employee.save()

            # Отправка электронной почты с паролем
            subject = 'Ваш новый пароль'
            message = f'Здравствуйте, {employee.first_name}!\n\nВаш новый пароль: {password}\n'
            email = EmailMessage(subject, message, to=[employee.email])
            email.send()

            return Response({
                'message': 'Registration successful',
                'generated_password': password  # Можете убрать эту строку, если не хотите возвращать пароль в ответе
            }, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@permission_classes([IsAdmin])
@api_view(['POST'])
def create_theme(request):
    if request.method == 'POST':
        serializer = ThemeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
@api_view(['GET'])
def get_all_tests(request):
    if request.method == 'GET':
        tests = Test.objects.all()
        serializer = TestSerializer(tests, many=True)
        return Response(serializer.data)
@api_view(['GET'])
def get_all_users(request):
    users = Employee.objects.all()
    serializer = EmployeeSerializer(users, many=True)
    return Response(serializer.data)
@api_view(['GET'])
def theme_list(request):
    if request.method == 'GET':
        themes = Theme.objects.all().order_by('name')
        serializer = ThemeSerializer(themes, many=True)
        return Response(serializer.data)


def get_karma_history(request, employee_id):
    try:
        employee = Employee.objects.get(id=employee_id)
        karma_history = KarmaHistory.objects.filter(employee=employee).order_by('-change_date')

        history_data = []
        for record in karma_history:
            history_data.append({
                'change_date': record.change_date.strftime('%Y-%m-%d %H:%M:%S'),
                'karma_change': record.karma_change,
                'reason': record.reason
            })

        return JsonResponse({'employee': employee.username, 'karma_history': history_data})
    except Employee.DoesNotExist:
        return JsonResponse({'error': 'Employee does not exist.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_POST
def reset_karma_update(request, employee_id):
    try:
        employee = Employee.objects.get(id=employee_id)
        if not employee.last_karma_update:
            return JsonResponse({'error': 'No karma update to reset.'}, status=400)

        # Найдем все изменения кармы после последнего обновления
        karma_changes = KarmaHistory.objects.filter(employee=employee, change_date__gte=employee.last_karma_update)

        # Откатим карму
        for change in karma_changes:
            employee.karma -= change.karma_change
            change.delete()

        # Сбросим дату последнего обновления кармы
        employee.last_karma_update = None
        employee.save()

        return JsonResponse({'success': 'Karma update reset and changes reverted.'})

    except Employee.DoesNotExist:
        return JsonResponse({'error': 'Employee does not exist.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

class PlayersViewSet(BasePermissionViewSet):
    queryset = Employee.objects.all()
    serializer_class = PlayersSerializer
    permission_classes = [IsAuthenticated]


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_feedback(request, type, employee_id):
    if type not in dict(Feedback.FEEDBACK_TYPE_CHOICES).keys():
        return Response({'error': 'Invalid feedback type provided'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        target_employee = Employee.objects.get(pk=employee_id)
    except Employee.DoesNotExist:
        return Response({'error': 'Target employee not found'}, status=status.HTTP_404_NOT_FOUND)

    data = request.data.copy()
    data['type'] = type
    data['target_employee'] = employee_id
    data['status'] = 'pending'
    data['moderation_comment'] = data.get('moderation_comment', None)  # Устанавливаем null, если комментарий не передан

    serializer = FeedbackSerializer(data=data)
    if serializer.is_valid():
        feedback = serializer.save()

        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



@api_view(['POST'])
@permission_classes([IsModeratorOrAdmin])
def moderate_feedback(request, feedback_id):
    try:
        feedback = Feedback.objects.get(pk=feedback_id)
    except Feedback.DoesNotExist:
        return Response({'error': 'Feedback not found'}, status=status.HTTP_404_NOT_FOUND)

    # Если карма или опыт были изменены вручную, то устанавливаем статус "pending"
    if feedback.status != 'pending' and (feedback.karma_change != 0 or feedback.experience_change != 0):
        feedback.status = 'pending'

    if feedback.status == 'pending':
        data = request.data
        action = data.get('action')
        level = data.get('level', None)
        karma_change = data.get('karma_change', None)
        experience_change = data.get('experience_change', 0)  # Допустим, опыт можно передавать тоже вручную
        moderation_comment = data.get('moderation_comment', '')

        if action == 'approve':
            if level is not None:
                # Используем уровень для расчета изменений кармы и опыта
                changes = calculate_karma_change(feedback.type, level)
                feedback.level = level
                feedback.karma_change = changes['karma_change']
                feedback.experience_change = changes['experience_change']
            elif karma_change is not None:
                # Если уровень не указан, но указано изменение кармы, используем его напрямую
                feedback.karma_change = karma_change
                feedback.experience_change = experience_change
            else:
                return Response({'error': 'Either level or karma_change is required for approving feedback'},
                                status=status.HTTP_400_BAD_REQUEST)

            # Применяем изменения к целевому сотруднику
            target_employee = feedback.target_employee
            if feedback.type == 'praise':
                target_employee.karma += feedback.karma_change
            else:
                target_employee.karma -= feedback.karma_change

            # Применяем изменения опыта, если они есть
            if feedback.experience_change:
                target_employee.add_experience(feedback.experience_change, source="За модерацию аваций")

            target_employee.save()
            feedback.status = 'approved'
        elif action == 'reject':
            feedback.status = 'rejected'
            feedback.karma_change = 0
            feedback.experience_change = 0
        else:
            return Response({'error': 'Invalid action provided'}, status=status.HTTP_400_BAD_REQUEST)

        feedback.moderator = request.user
        feedback.moderation_comment = moderation_comment
        feedback.moderation_date = timezone.now()
        feedback.save()

        serializer = FeedbackSerializer(feedback)
        return Response(serializer.data, status=status.HTTP_200_OK)
    else:
        return Response({'error': 'Status must be pending'}, status=status.HTTP_400_BAD_REQUEST)



def calculate_karma_change(operation_type, level=None):
    try:
        if level is not None:
            karma_setting = KarmaSettings.objects.get(operation_type=operation_type, level=level)
        else:
            karma_setting = KarmaSettings.objects.get(operation_type=operation_type, level__isnull=True)

        return {
            "karma_change": karma_setting.karma_change or 0,
            "experience_change": karma_setting.experience_change or 0
        }
    except KarmaSettings.DoesNotExist:
        return {
            "karma_change": 0,
            "experience_change": 0
        }  # Или значения по умолчанию, если настройки не найдены


class LevelTitleViewSet(BasePermissionViewSet):
    permission_classes = [IsAdminUser]

    @action(detail=False, methods=['post'])
    def create_levels(self, request):
        levels = request.data.get('levels', [])

        if not levels:
            return Response({"message": "No levels provided"}, status=status.HTTP_400_BAD_REQUEST)

        created_levels = []
        for i, title in enumerate(levels, start=1):
            level_title, created = LevelTitle.objects.update_or_create(level=i, defaults={'title': title})
            created_levels.append({'level': level_title.level, 'title': level_title.title})

        return Response({
            "message": "Levels created/updated successfully",
            "created_levels": created_levels
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['put'])
    def update_level(self, request, pk=None):
        try:
            level_title = LevelTitle.objects.get(level=pk)
            level_title.title = request.data.get('title', level_title.title)
            level_title.save()
            return Response({"message": "Level updated successfully", "level": pk, "title": level_title.title})
        except LevelTitle.DoesNotExist:
            return Response({"message": "Level not found"}, status=status.HTTP_404_NOT_FOUND)
#########
    @action(detail=False, methods=['get'])
    def list_levels(self, request):
        levels = LevelTitle.objects.all()
        data = [{'level': lt.level, 'title': lt.title} for lt in levels]
        return Response(data, status=status.HTTP_200_OK)


from openpyxl import load_workbook
import pandas as pd

class FileUploadAndAnalysisView(APIView):
    def post(self, request):
        start_time = time.time()  # Засекаем время начала
        file = request.FILES.get('file')
        if not file:
            return Response({"message": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)
        print(f"Received file: {file.name} at {time.time() - start_time} seconds")

        if "Тип обращений" in file.name:
            print(f"Detected 'Тип обращений' in file name at {time.time() - start_time} seconds")
            file_path_entry = FilePath.objects.get(name="Requests")
        elif self.has_date_format(file.name):
            print(f"Detected date format in file name: {file.name} at {time.time() - start_time} seconds")
            file_path_entry = FilePath.objects.get(name="Work Schedule")
        else:
            print(f"Unknown file type or incorrect date format for file: {file.name}")
            return Response({"message": "Unknown file type or incorrect date format"},
                            status=status.HTTP_400_BAD_REQUEST)

        directory_path = file_path_entry.path
        if not os.path.exists(directory_path):
            return Response({"message": f"Directory does not exist: {directory_path}"},
                            status=status.HTTP_400_BAD_REQUEST)

        # Сохранение файла в указанную директорию с использованием контекстного менеджера
        destination_file_path = os.path.join(directory_path, file.name)
        with open(destination_file_path, 'wb+') as destination_file:
            for chunk in file.chunks():
                destination_file.write(chunk)
        print(f"File saved at {time.time() - start_time} seconds")

        # Проверка файла с помощью openpyxl перед запуском дальнейшего анализа
        try:
            wb = load_workbook(destination_file_path)
            print(f"Файл успешно открыт с помощью openpyxl: {file.name} at {time.time() - start_time} seconds")
        except Exception as e:
            print(f"Ошибка при открытии файла с помощью openpyxl: {e}")
            return Response({"message": f"Error processing file: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        # Запуск соответствующего скрипта на основе имени файла
        if "Тип обращений" in file.name:
            self.run_classifications_script(destination_file_path)
        elif self.has_date_format(file.name):
            self.run_schedule_script(destination_file_path)
        else:
            return Response({"message": "Unknown file type or incorrect date format"},
                            status=status.HTTP_400_BAD_REQUEST)

        print(f"Completed at {time.time() - start_time} seconds")
        return Response({"message": "File processed successfully"}, status=status.HTTP_200_OK)

    def run_classifications_script(self, file_path):
        try:
            from scripts.class_script import run_classification_script
            file_path_entry = FilePath.objects.get(name="Requests")
            run_classification_script(file_path, file_path_entry)  # Передаем объект `file_path_entry`
            print(f"Classification script executed for file: {file_path}")
        except Exception as e:
            print(f"Error running classification script: {e}")

    def run_schedule_script(self, file_path):
        try:
            from scripts.tasks import update_employee_karma
            update_employee_karma(file_path)
            print(f"Schedule script executed for file: {file_path}")
        except Exception as e:
            print(f"Error running schedule script: {e}")
    def has_date_format(self, filename):
        # Регулярное выражение теперь включает проверку расширения .xlsx
        date_pattern = r'\d{2}\.\d{2}\.\d{4}\.xlsx$'  # dd.mm.yyyy.xlsx
        match = re.search(date_pattern, filename)
        print(
            f"Date format check for filename '{filename}': Match found: {bool(match)}, Matched text: {match.group(0) if match else 'None'}")
        return bool(match)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_micro_user(request):
    try:
        # Получаем текущего сотрудника по токену
        current_employee = request.user
        employee_id = request.query_params.get('employee_id', None)

        # Если передан employee_id, получаем сотрудника по этому id, иначе берем текущего пользователя
        if employee_id:
            employee = get_object_or_404(Employee, id=employee_id)
        else:
            employee = current_employee

        # Сериализуем данные сотрудника
        serializer = MicroEmployeeSerializer(employee)

        # Возвращаем данные в ответе
        return Response(serializer.data)

    except Exception as e:
        return Response({"error": str(e)}, status=400)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user(request):
    try:
        current_employee = request.user
        employee_id = request.query_params.get('employee_id', None)

        if employee_id:
            employee = get_object_or_404(Employee, id=employee_id)
        else:
            employee = current_employee

        serializer = EmployeeSerializer(employee, context={'request': request})

        # Вычисление периодов времени
        today = timezone.now()
        start_of_week = today - timedelta(days=today.weekday())  # Начало недели (понедельник)
        start_of_month = today.replace(day=1)  # Начало месяца

        # Подсчёт заработанного опыта за месяц и неделю (только положительные изменения)
        total_experience_earned_month = EmployeeLog.objects.filter(
            employee=employee,
            change_type='experience',
            timestamp__year=today.year,
            timestamp__month=today.month,
            new_value__gt=F('old_value')  # Только положительные изменения
        ).annotate(gain=F('new_value') - F('old_value')).aggregate(total=Sum('gain'))['total'] or 0

        total_experience_earned_week = EmployeeLog.objects.filter(
            employee=employee,
            change_type='experience',
            timestamp__gte=start_of_week,
            new_value__gt=F('old_value')  # Только положительные изменения
        ).annotate(gain=F('new_value') - F('old_value')).aggregate(total=Sum('gain'))['total'] or 0

        # Подсчёт общего заработанного опыта (все положительные изменения)
        total_experience_earned = EmployeeLog.objects.filter(
            employee=employee,
            change_type='experience',
            new_value__gt=F('old_value')  # Только положительные изменения
        ).annotate(gain=F('new_value') - F('old_value')).aggregate(total=Sum('gain'))['total'] or 0

        # Подсчёт заработанных A-коинов за месяц и неделю
        total_acoins_month = AcoinTransaction.objects.filter(
            employee=employee,
            timestamp__gte=start_of_month
        ).aggregate(total=Sum('amount'))['total'] or 0

        total_acoins_week = AcoinTransaction.objects.filter(
            employee=employee,
            timestamp__gte=start_of_week
        ).aggregate(total=Sum('amount'))['total'] or 0

        # Общий подсчёт A-коинов
        total_acoins = AcoinTransaction.objects.filter(employee=employee).aggregate(total=Sum('amount'))['total'] or 0

        # Остальные данные профиля, статистика
        registration_date = employee.date_joined.strftime('%Y-%m-%d')
        last_login = employee.last_login.strftime('%Y-%m-%d %H:%M:%S') if employee.last_login else 'Never'
        completed_tests_count = TestAttempt.objects.filter(employee=employee, status=TestAttempt.PASSED).count()

        complaints_count = Feedback.objects.filter(target_employee=employee, type="complaint", status='approved').count()
        praises_count = Feedback.objects.filter(target_employee=employee, type="praise", status='approved').count()
        praises = Feedback.objects.filter(target_employee=employee, type="praise", status='approved')

        # Ответы на вопросы опроса
        survey_questions = SurveyQuestion.objects.all()
        survey_answers = SurveyAnswer.objects.filter(employee=employee)
        answers_with_text = []
        answers_without_text = []

        for question in survey_questions:
            answer = survey_answers.filter(question=question).first()
            if question.question_text.lower() == "дата рождения":
                if employee.birth_date:
                    birth_date_str = employee.birth_date.strftime('%Y-%m-%d')
                    answers_with_text.append({
                        "question_id": question.id,
                        "question_text": question.question_text,
                        "answer_text": birth_date_str
                    })
                    continue
            if answer and answer.answer_text:
                answers_with_text.append({
                    "question_id": question.id,
                    "question_text": question.question_text,
                    "answer_text": answer.answer_text
                })
            else:
                answers_without_text.append({
                    "question_id": question.id,
                    "question_text": question.question_text,
                    "answer_text": ""
                })
        answers = answers_with_text + answers_without_text

        # Достижения сотрудника
        employee_achievements = EmployeeAchievement.objects.filter(employee=employee)
        employee_achievements_data = EmployeeAchievementSerializer(employee_achievements, many=True).data
        achievements_count = employee_achievements.count()

        # Обращения
        requests_qs = Request.objects.filter(support_operator=employee).select_related('classification')
        requests_massive_qs = requests_qs.filter(is_massive=True)

        total_requests = requests_qs.count()
        requests_this_month = requests_qs.filter(date__year=today.year, date__month=today.month).count()
        requests_this_week = requests_qs.filter(date__gte=start_of_week).count()

        total_requests_massive = requests_massive_qs.count()
        requests_massive_this_month = requests_massive_qs.filter(date__year=today.year, date__month=today.month).count()
        requests_massive_this_week = requests_massive_qs.filter(date__gte=start_of_week).count()

        # Группировка по классификациям с подсчетом за месяц и неделю
        classifications = requests_qs.values('classification__name').annotate(
            total=Count('number'),
            month=Count('number', filter=Q(date__year=today.year, date__month=today.month)),
            week=Count('number', filter=Q(date__gte=start_of_week))
        )
        grouped_requests = [
            {
                'classification_name': c['classification__name'],
                'total': c['total'],
                'month': c['month'],
                'week': c['week'],
            }
            for c in classifications
        ]

        # Массивы для вывода данных по обращениям (вложенные массивы)
        request_statistics = [
            [
                {
                    'titleName': 'Общие обращения',
                    'contentPoint': [
                        f'Всего: {total_requests}',
                        f'За месяц: {requests_this_month}',
                        f'За неделю: {requests_this_week}'
                    ],
                },
                {
                    'titleName': 'Массовые обращения',
                    'contentPoint': [
                        f'Всего массовых обращений: {total_requests_massive}',
                        f'За месяц: {requests_massive_this_month}',
                        f'За неделю: {requests_massive_this_week}'
                    ]
                }
            ],
            [
                {
                    'titleName': 'Обращения по классификациям',
                    'contentPoint': [
                        f'{item["classification_name"]}: {item["total"]} обращений (Месяц: {item["month"]}, Неделя: {item["week"]})'
                        for item in grouped_requests
                    ]
                }
            ]
        ]

        # Количество отработанных дней
        worked_days = ShiftHistory.objects.filter(employee=employee).values('date').distinct().count()

        # Количество опозданий
        total_lates = ShiftHistory.objects.filter(
            employee=employee,
            actual_start__gt=F('scheduled_start')
        ).count()

        # Наибольшее количество дней без опозданий
        shift_history = ShiftHistory.objects.filter(employee=employee).order_by('date')
        max_days_without_late = 0
        current_streak = 0
        last_date = None
        for shift in shift_history:
            if shift.actual_start <= shift.scheduled_start:
                if last_date and (shift.date - last_date).days == 1:
                    current_streak += 1
                else:
                    current_streak = 1
                max_days_without_late = max(max_days_without_late, current_streak)
            else:
                current_streak = 0
            last_date = shift.date

        # Инвентарь сотрудника
        employee_items = EmployeeItem.objects.filter(employee=employee)
        employee_items_data = EmployeeItemSerializer(employee_items, many=True).data

        # Собираем основную информацию для профиля
        profile_statistics = [
            {
                "titleName": "Основная информация",
                "contentPoint": [
                    f"Дата регистрации профиля: {registration_date}",
                    f"Кол-во отработанных дней: {worked_days}",
                    f"Опозданий всего: {total_lates}",
                    f"Максимум дней без опозданий: {max_days_without_late}",
                    f"Заработано тестов: {completed_tests_count}",
                    f"Жалоб: {complaints_count}",
                    f"Похвал: {praises_count}"
                ]
            },
            {
                "titleName": "Заработанный опыт",
                "contentPoint": [
                    f"Всего: {total_experience_earned}",
                    f"За месяц: {total_experience_earned_month}",
                    f"За неделю: {total_experience_earned_week}"
                ]
            },
            {
                "titleName": "Заработанные A-Коины",
                "contentPoint": [
                    f"Всего: {total_acoins}",
                    f"За месяц: {total_acoins_month}",
                    f"За неделю: {total_acoins_week}"
                ]
            }
        ]

        # Собираем статистику по обращениям
        statistics_requests = request_statistics  # Уже является списком списков

        # Объединяем основную статистику и статистику по обращениям
        statistics = [
            profile_statistics,  # Первая "страница"
            statistics_requests  # Вторая "страница"
        ]

        # Достижения сотрудника
        # Похвалы остаются отдельным ключом "praises_details"

        return Response({
            'profile': serializer.data,
            'level_title': employee.level_title,
            'statistics': statistics,  # Список списков
            'praises_details': FeedbackSerializer(praises, many=True).data,  # Оставляем отдельным
            'answers': answers,
            'achievements': employee_achievements_data,
            'inventory': employee_items_data,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
@api_view(['GET'])
@permission_classes([IsAuthenticated, partial(HasPermission, perm='main.can_view_complaints')])
def get_employee_complaints(request, employee_id):
    try:
        # Получаем сотрудника, жалобы на которого нужно показать
        employee = get_object_or_404(Employee, id=employee_id)

        # Получаем одобренные жалобы на этого сотрудника
        complaints = Feedback.objects.filter(target_employee=employee, type="complaint", status='approved')

        return Response({
            'complaints': FeedbackSerializer(complaints, many=True).data,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)




class FeedbackDetailView(generics.RetrieveAPIView):
    queryset = Feedback.objects.all()
    serializer_class = FeedbackSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Дополнительные фильтры или логика, если потребуется
        return super().get_queryset()

class EmployeeLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint для просмотра логов изменений сотрудников.
    """
    queryset = EmployeeLog.objects.all().order_by('-timestamp')
    serializer_class = EmployeeLogSerializer

class SurveyQuestionView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def post(self, request):
        questions_data = request.data.get('questions', [])

        if not questions_data:
            return Response({"message": "No questions provided"}, status=status.HTTP_400_BAD_REQUEST)

        created_questions = []

        for question_data in questions_data:
            serializer = SurveyQuestionSerializer(data=question_data)
            if serializer.is_valid():
                question = serializer.save()
                created_questions.append(serializer.data)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "message": "Questions created successfully",
            "created_questions": created_questions
        }, status=status.HTTP_201_CREATED)

    def get(self, request):
        try:
            questions = SurveyQuestion.objects.all()
            serializer = SurveyQuestionSerializer(questions, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_survey_answers(request):
    try:
        employee = request.user
        answers = request.data.get('answers', [])

        for answer_data in answers:
            question_id = answer_data.get('question_id')
            answer_text = answer_data.get('answer_text')

            try:
                question = SurveyQuestion.objects.get(id=question_id)
            except SurveyQuestion.DoesNotExist:
                return Response({'error': f'Question with ID {question_id} not found'}, status=status.HTTP_404_NOT_FOUND)

            # Сохранение ответа на вопрос
            SurveyAnswer.objects.update_or_create(
                employee=employee,
                question=question,
                defaults={'answer_text': answer_text}
            )

        return Response({"message": "Answers submitted successfully"}, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
class ClassificationsViewSet(BasePermissionViewSet):
    queryset = Classifications.objects.all()
    serializer_class = ClassificationsSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def tree(self, request):
        root_nodes = Classifications.objects.filter(parent__isnull=True)
        serializer = self.get_serializer(root_nodes, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def leaf_nodes(self, request):
        # Фильтрация классификаций, у которых нет подкатегорий (subclassifications)
        leaf_nodes = Classifications.objects.annotate(subclassifications_count=Count('subclassifications')).filter(subclassifications_count=0)
        serializer = self.get_serializer(leaf_nodes, many=True)

        return Response(serializer.data)
class SurveyQuestionViewSet(BasePermissionViewSet):
    queryset = SurveyQuestion.objects.all()
    serializer_class = SurveyQuestionSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        if isinstance(request.data, list):
            serializer = self.get_serializer(data=request.data, many=True)
            serializer.is_valid(raise_exception=True)
            self.perform_bulk_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response({"detail": "Invalid data. Expected a list of dictionaries."}, status=status.HTTP_400_BAD_REQUEST)

    def perform_bulk_create(self, serializer):
        SurveyQuestion.objects.bulk_create([SurveyQuestion(**data) for data in serializer.validated_data])

class SurveyAnswerViewSet(BasePermissionViewSet):
    queryset = SurveyAnswer.objects.all()
    serializer_class = SurveyAnswerSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(employee=self.request.user)

class EmployeeActionLogViewSet(BasePermissionViewSet):
    queryset = EmployeeActionLog.objects.all().order_by('-created_at')
    serializer_class = EmployeeActionLogSerializer
    permission_classes = [IsAuthenticated]

class GroupViewSet(BasePermissionViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer

    extra_permission_classes = {
        # Если нужно задать специфическое право для нестандартного действия
        'custom_action': [partial(HasPermission, perm='custom_permission')]
    }
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)


class PermissionManagementViewSet(BasePermissionViewSet):
    queryset = Permission.objects.none()  # Фиктивный queryset

    @action(detail=False, methods=['get'])
    def list_permissions(self, request):
        permissions = Permission.objects.all().order_by('id')
        serializer = PermissionSerializer(permissions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def assign_permission_to_user(self, request, pk=None):
        user = get_object_or_404(Employee, pk=pk)
        permission = get_object_or_404(Permission, id=request.data.get('permission_id'))
        user.user_permissions.add(permission)
        return Response({'status': 'permission assigned'})

    @action(detail=True, methods=['post'])
    def remove_permission_from_user(self, request, pk=None):
        user = get_object_or_404(Employee, pk=pk)
        permission = get_object_or_404(Permission, id=request.data.get('permission_id'))
        user.user_permissions.remove(permission)
        return Response({'status': 'permission removed'})

    @action(detail=True, methods=['post'])
    def assign_permission_to_group(self, request, pk=None):
        group = get_object_or_404(Group, pk=pk)
        permission = get_object_or_404(Permission, id=request.data.get('permission_id'))
        group.permissions.add(permission)
        return Response({'status': 'permission assigned'})

    @action(detail=True, methods=['post'])
    def remove_permission_from_group(self, request, pk=None):
        group = get_object_or_404(Group, pk=pk)
        permission = get_object_or_404(Permission, id=request.data.get('permission_id'))
        group.permissions.remove(permission)
        return Response({'status': 'permission removed'})

    @action(detail=True, methods=['get'])
    def list_user_permissions(self, request, pk=None):
        user = get_object_or_404(Employee, pk=pk)
        permissions = user.user_permissions.all()
        serializer = PermissionSerializer(permissions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def list_group_permissions(self, request, pk=None):
        group = get_object_or_404(Group, pk=pk)
        permissions = group.permissions.all()
        serializer = PermissionSerializer(permissions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def list_groups(self, request):
        groups = Group.objects.all()
        serializer = GroupSerializer(groups, many=True)
        return Response(serializer.data)


@api_view(['GET'])
@permission_classes([partial(HasPermission, perm='main.view_system_statistics')])
def system_statistics(request):
    # 1. Активные пользователи
    active_users = get_active_users(minutes=5).values_list('username', flat=True)
    active_users_count = active_users.count()

    # 2. Общее количество зарегистрированных пользователей
    users = Employee.objects.all().values('username', 'date_joined')  # Используем 'date_joined' для даты регистрации
    total_users_count = Employee.objects.count()

    # 3. Количество деактивированных пользователей
    deactivated_users_count = Employee.objects.filter(is_active=False).count()
    deactivated_users = Employee.objects.filter(is_active=False).values_list('username', flat=True)

    # 4. Количество созданных тестов и их названия
    tests = Test.objects.all().values('name')
    total_tests_count = tests.count()

    # 5. Получить тесты, где есть успешные попытки прохождения
    successful_tests = (
        Test.objects.annotate(
            passed_attempts=Count('testattempt', filter=Q(testattempt__status=TestAttempt.PASSED))
        ).filter(passed_attempts__gt=0)
        .values('name', 'passed_attempts')
    )

    # 6. Получить тесты, которые были модерированы
    moderated_tests = []
    moderated_tests_queryset = TestAttempt.objects.filter(test_results__icontains='moderator')

    # Обработка результатов вручную
    for attempt in moderated_tests_queryset:
        test_result = json.loads(attempt.test_results)
        if 'moderator' in test_result:
            test_name = attempt.test.name
            moderated_test = next((item for item in moderated_tests if item['name'] == test_name), None)
            if moderated_test:
                moderated_test['moderated_attempts'] += 1
            else:
                moderated_tests.append({'name': test_name, 'moderated_attempts': 1})

    # Подготовка ответа
    data = {
        'active_users_count': active_users_count,
        'active_users': list(active_users),
        'total_users_count': total_users_count,
        'users': list(users),  # Возвращаем список пользователей с их датами регистрации
        'deactivated_users_count': deactivated_users_count,
        'deactivated_users':deactivated_users,
        'total_tests_count': total_tests_count,
        'tests': list(tests),
        'successful_tests': list(successful_tests),
        'moderated_tests': moderated_tests,
    }

    return Response(data)
class ExperienceMultiplierViewSet(BasePermissionViewSet):
    queryset = ExperienceMultiplier.objects.all()
    serializer_class = ExperienceMultiplierSerializer
class KarmaSettingsViewSet(BasePermissionViewSet):
    queryset = KarmaSettings.objects.all()
    serializer_class = KarmaSettingsSerializer

class FilePathViewSet(BasePermissionViewSet):
    queryset = FilePath.objects.all()
    serializer_class = FilePathSerializer
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_late_penalty_settings(request):
    try:
        late_penalty_settings = request.data.get('late_penalty_settings', [])

        for setting_data in late_penalty_settings:
            level = setting_data.get('level')
            karma_change = setting_data.get('karma_change')

            if level is not None:
                karma_setting = KarmaSettings.objects.filter(operation_type='late_penalty', level=level).first()
                if karma_setting:
                    karma_setting.karma_change = karma_change
                    karma_setting.save()

        return Response({"message": "Настройки опозданий успешно обновлены."}, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_late_penalty_settings(request):
    late_penalty_settings = KarmaSettings.objects.filter(operation_type='late_penalty').order_by('level')
    serializer = KarmaSettingsSerializer(late_penalty_settings, many=True)
    return Response(serializer.data)
class KarmaSettingsUpdateView(APIView):
    def post(self, request):
        serializer = KarmaUpdateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Karma settings updated successfully"}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
def delete_inactive_sessions():
    # Определяем пороговую дату для удаления сессий (например, сессии, неактивные более 30 дней)
    threshold_date = timezone.now() - timedelta(days=30)

    # Удаление всех сессий, которые были активны до пороговой даты
    Session.objects.filter(expire_date__lt=threshold_date).delete()
    print("Неактивные сессии успешно удалены")

class SessionListView(APIView):
    def get(self, request):
        # Получение всех активных сессий
        sessions = Session.objects.all()
        session_data = []

        for session in sessions:
            session_info = {
                'session_key': session.session_key,
                'expire_date': session.expire_date,
                'data': session.get_decoded(),  # Расшифровка данных сессии
            }
            session_data.append(session_info)

        return Response(session_data, status=status.HTTP_200_OK)

    def delete(self, request):
        # Удаление всех неактивных сессий
        delete_inactive_sessions()
        return Response({"message": "Неактивные сессии удалены"}, status=status.HTTP_200_OK)

# InventoryView - просмотр инвентаря сотрудника
class InventoryView(APIView):
    def get(self, request):
        employee_items = EmployeeItem.objects.filter(employee=request.user)

        # Проверяем срок действия предметов
        for employee_item in employee_items:
            employee_item.check_expiration()

        serializer = EmployeeItemSerializer(employee_items, many=True)
        return Response(serializer.data)

# StoreView - покупка и просмотр доступных предметов
class StoreView(APIView):
    def get(self, request):
        items = Item.objects.all()  # Все доступные предметы
        serializer = ItemSerializer(items, many=True)
        return Response(serializer.data)

    def post(self, request):
        item_id = request.data.get('item_id')
        try:
            item = Item.objects.get(id=item_id)
        except Item.DoesNotExist:
            return Response({"message": "Item not found"}, status=status.HTTP_404_NOT_FOUND)

        employee = request.user  # Текущий пользователь

        # Получаем аcoin'ы сотрудника
        employee_acoin = employee.acoin

        # Проверяем, не купил ли сотрудник уже этот предмет (если такая логика нужна)
        if EmployeeItem.objects.filter(employee=employee, item=item).exists():
            return Response({"message": "Item already purchased"}, status=status.HTTP_400_BAD_REQUEST)

        # Проверка на достаточное количество акоинов
        if employee_acoin.amount >= item.price:
            # Списываем цену предмета с баланса акоинов
            old_acoin_amount = employee_acoin.amount
            employee_acoin.amount -= item.price
            employee_acoin.save()

            # Логируем транзакцию покупки
            AcoinTransaction.objects.create(
                employee=employee,
                amount=-item.price,  # Отрицательное значение указывает на трату акоинов
                timestamp=timezone.now()
            )

            # Логируем изменения акоинов у сотрудника
            employee.log_change(
                'acoins',
                old_acoin_amount,
                employee_acoin.amount,
                source='Покупка предмета',
                description=f"{employee.get_full_name()} приобрел {item.description} за {item.price} акоинов"
            )

            # Добавляем предмет в инвентарь
            EmployeeItem.objects.create(employee=employee, item=item)
            return Response({"message": "Item purchased successfully"})
        else:
            return Response({"message": "Not enough akoins"}, status=status.HTTP_400_BAD_REQUEST)


class SystemSettingViewSet(BasePermissionViewSet):
    queryset = SystemSetting.objects.all()
    serializer_class = SystemSettingSerializer

    # Список всех настроек
    @action(detail=False, methods=['get'])
    def list_settings(self, request):
        settings = SystemSetting.objects.all()
        serializer = SystemSettingSerializer(settings, many=True)
        return Response(serializer.data)

    # Обновление или создание настройки по ключу
    @action(detail=False, methods=['post'])
    def update_setting(self, request):
        key = request.data.get('key')
        value = request.data.get('value')

        if not key or not value:
            return Response({"error": "Both 'key' and 'value' are required."}, status=status.HTTP_400_BAD_REQUEST)

        setting, created = SystemSetting.objects.get_or_create(key=key)
        setting.value = value
        setting.save()

        return Response({'message': f'Setting {key} updated', 'key': key, 'value': value})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def select_avatar(request):
    try:
        avatar_id = request.data.get('avatar_id')
        if not avatar_id:
            return Response({'error': 'Avatar ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Получаем аватарку из пула
        avatar = PreloadedAvatar.objects.get(pk=avatar_id)

        # Устанавливаем аватарку для текущего пользователя
        request.user.avatar = avatar.image
        request.user.save()

        return Response({'message': 'Avatar updated successfully'}, status=status.HTTP_200_OK)
    except PreloadedAvatar.DoesNotExist:
        return Response({'error': 'Avatar not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PreloadedAvatarUploadViewSet(BasePermissionViewSet):
    queryset = PreloadedAvatar.objects.all()
    serializer_class = PreloadedAvatarSerializer
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        file_path = FilePath.objects.filter(name='Avatars').first()
        if not file_path:
            raise serializers.ValidationError("FilePath for 'Avatars' not found.")

        original_image = self.request.FILES['image']
        new_image_path = os.path.join(file_path.path, original_image.name)

        # Сохраняем изображение в указанную папку
        with open(new_image_path, 'wb+') as destination:
            for chunk in original_image.chunks():
                destination.write(chunk)

        # Сохраняем путь в базе данных (в формате относительно media root)
        relative_image_path = os.path.join('avatars', original_image.name)
        serializer.save(image=relative_image_path)


    def perform_update(self, serializer):
        file_path = FilePath.objects.filter(name='Avatars').first()
        if not file_path:
            raise serializers.ValidationError("FilePath for 'Avatars' not found.")

        original_image = self.request.FILES['image']
        new_image_path = os.path.join(file_path.path, original_image.name)

        # Сохраняем изображение в указанную папку
        with open(new_image_path, 'wb+') as destination:
            for chunk in original_image.chunks():
                destination.write(chunk)

        # Сохраняем путь в базе данных (в формате относительно media root)
        relative_image_path = os.path.join('avatars', original_image.name)
        serializer.save(image=relative_image_path)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_avatar(request):
    avatar_id = request.data.get('avatar_id')

    if not avatar_id:
        return Response({'error': 'Avatar ID is required'}, status=400)

    avatar = get_object_or_404(PreloadedAvatar, id=avatar_id)

    employee = request.user
    employee.avatar = avatar.image
    employee.save()

    return Response({'message': 'Avatar updated successfully'}, status=200)


def get_active_users(minutes=5):
    time_threshold = timezone.now() - timedelta(minutes=minutes)
    active_users = Employee.objects.filter(last_login__gte=time_threshold, is_active=True)
    return active_users
@permission_classes([IsAdmin])
@api_view(['DELETE'])
def delete_all_tests(request):
    if request.method == 'DELETE':
        # Получаем все объекты модели Test
        tests = Test.objects.all()

        # Удаляем все тесты
        tests.delete()

        return Response({"message": "All tests have been deleted"}, status=status.HTTP_204_NO_CONTENT)
@api_view(['POST'])
def set_file_path(request):
    name = request.data.get('name', '')
    path = request.data.get('path', '')
    if name and path:
        file_path, created = FilePath.objects.get_or_create(name=name)
        file_path.path = path
        file_path.save()
        return Response({"message": f"File path for {name} updated successfully"}, status=status.HTTP_200_OK)
    else:
        return Response({"error": "Name and path not provided"}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def get_user_balance(request, user_id):
    try:
        acoin = Acoin.objects.get(employee_id=user_id)
        serializer = AcoinSerializer(acoin)
        return Response(serializer.data)
    except Acoin.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
def get_user_transactions(request, user_id):
    try:
        transactions = AcoinTransaction.objects.filter(employee_id=user_id)
        serializer = AcoinTransactionSerializer(transactions, many=True)
        return Response(serializer.data)
    except AcoinTransaction.DoesNotExist:
        return Response({'error': 'Transactions not found'}, status=404)


@api_view(['GET'])
def get_test_with_theory(request, test_id):
    try:
        # Получаем тест по его идентификатору
        test = Test.objects.get(id=test_id)

        # Получаем все вопросы для этого теста
        questions = TestQuestion.objects.filter(test=test)

        data = []

        # Проходимся по каждому вопросу
        for question in questions:
            # Получаем все теории для этого вопроса
            theories = Theory.objects.filter(test=test).order_by('position')

            # Добавляем теории и вопросы в порядке их позиции
            for block in theories:
                data.append({
                    'type': 'theory',
                    'text': block.text
                })

            data.append({
                'type': 'question',
                'question_text': question.question_text,
                'question_type': question.question_type,
                'points': question.points,
                'explanation': question.explanation,
                'answer_options': [
                    {
                        'option_text': option.option_text,
                        'is_correct': option.is_correct
                    }
                    for option in question.answer_options.all()
                ]
            })

        return Response(data)
    except Test.DoesNotExist:
        return Response({'error': 'Test not found'}, status=404)

@permission_classes([IsAdmin])
class UpdateTestAndContent(APIView):
    def put(self, request, test_id):
        return self.update_test_and_content(request, test_id, partial=False)

    def patch(self, request, test_id):
        return self.update_test_and_content(request, test_id, partial=True)

    def update_test_and_content(self, request, test_id, partial):
        try:
            test = Test.objects.get(id=test_id)
        except Test.DoesNotExist:
            return Response({"message": "Test not found"}, status=status.HTTP_404_NOT_FOUND)

        test_data = request.data.get('test', {})
        test_serializer = TestSerializer(test, data=test_data, partial=partial)
        if test_serializer.is_valid():
            test_serializer.save()

            # Обработка вопросов
            if 'questions' in request.data:
                # Удаление старых вопросов
                test.questions.all().delete()
                questions_data = request.data['questions']
                for question_data in questions_data:
                    question_data['test'] = test.id  # Привязываем вопрос к тесту
                    question_serializer = TestQuestionSerializer(data=question_data)
                    if question_serializer.is_valid():
                        question_serializer.save()
                    else:
                        return Response(question_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            # Обработка ответов (если они включены в запрос)
            if 'answers' in request.data:
                AnswerOption.objects.filter(question__test=test).delete()  # Удаляем старые ответы
                answers_data = request.data['answers']
                for answer_data in answers_data:
                    answer_data['question'] = test.questions.first().id  # Привязываем ответ к первому вопросу как пример
                    answer_serializer = AnswerOptionSerializer(data=answer_data)
                    if answer_serializer.is_valid():
                        answer_serializer.save()
                    else:
                        return Response(answer_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            # Обработка теории
            if 'theory' in request.data:
                Theory.objects.filter(test=test).delete()  # Удаляем старую теорию
                theory_data = request.data['theory']
                theory_data['test'] = test.id  # Привязываем теорию к тесту
                theory_serializer = TheorySerializer(data=theory_data)
                if theory_serializer.is_valid():
                    theory_serializer.save()
                else:
                    return Response(theory_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            return Response({"message": "Test and content updated successfully"}, status=status.HTTP_200_OK)
        else:
            return Response(test_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([IsModeratorOrAdmin])
@api_view(['GET'])
def test_moderation_result(request, test_attempt_id):
    try:
        test_attempt = TestAttempt.objects.get(id=test_attempt_id, status=TestAttempt.MODERATION)
    except TestAttempt.DoesNotExist:
        return Response({"message": "Test attempt not found or not in moderation"}, status=status.HTTP_404_NOT_FOUND)

    # Формируем ответ, указывая статус теста
    response_data = {}

    # Если тест находится на модерации, возвращаем информацию о статусе и ничего больше не отображаем
    if test_attempt.status == TestAttempt.MODERATION:
        test = test_attempt.test
        test_results = json.loads(test_attempt.test_results)
        answers_info = test_results.get("answers_info", [])

        filtered_answers_info = [
            {
                "question_number": idx + 1,  # Добавляем номер вопроса (индекс + 1)
                "question_text": answer_info.get("question_text"),
                "text_answer": answer_info.get("text_answer"),
                "max_question_score": answer_info.get("max_question_score")
            }
            for idx, answer_info in enumerate(answers_info)
            if answer_info.get("type") == "text"
        ]

        response_data.update({
            "test": test.name,
            "answers_info": filtered_answers_info
        })

    return Response(response_data, status=status.HTTP_200_OK)


@api_view(['GET'])
def test_results(request, test_attempt_id):
    try:
        test_attempt = TestAttempt.objects.get(id=test_attempt_id)
    except TestAttempt.DoesNotExist:
        return Response({"message": "Test attempt not found"}, status=status.HTTP_404_NOT_FOUND)

    # Проверяем статус теста
    if test_attempt.status in [TestAttempt.MODERATION, TestAttempt.IN_PROGRESS]:
        response_data = {
            "status": test_attempt.status
        }
        return Response(response_data, status=status.HTTP_200_OK)

    try:
        test_results = json.loads(test_attempt.test_results)
    except (TypeError, JSONDecodeError):
        return Response({"message": "Invalid test results format"}, status=status.HTTP_400_BAD_REQUEST)

    test_id = test_attempt.test_id
    test = Test.objects.get(id=test_id)

    answers_info = test_results.get("answers_info", [])
    for answer_info in answers_info:
        if answer_info.get("type") == "multiple":
            correct_answers = [opt for opt in answer_info["answer_options"] if opt["correct_options"]]
            incorrect_answers = [opt for opt in answer_info["answer_options"] if not opt["correct_options"]]
            selected_correct = [opt for opt in correct_answers if opt["submitted_answer"]]
            selected_incorrect = [opt for opt in incorrect_answers if opt["submitted_answer"]]
            answer_info["is_partially_true"] = len(selected_correct) > 0 and len(selected_incorrect) > 0

    irkutsk_tz = pytz.timezone('Asia/Irkutsk')

    response_data = {
        "score": test_attempt.score,
        "max_score": test_results.get("Максимальное количество баллов"),
        "status": test_attempt.status,
        "answers_info": answers_info,
        "test_creation_date": localtime(test.created_at, irkutsk_tz).strftime("%Y-%m-%d %H:%M:%S") if test.created_at else None,
        "test_end_date": localtime(test_attempt.end_time, irkutsk_tz).strftime("%Y-%m-%d %H:%M:%S") if test_attempt.end_time else None,
        "employee": {
            "id": test_attempt.employee.id,
            "name": f"{test_attempt.employee.first_name} {test_attempt.employee.last_name}"
        },
        "duration_seconds": (
            test_attempt.end_time - test_attempt.start_time).total_seconds() if test_attempt.end_time else None
    }


    moderation_comment = test_results.get("moderation_comment", "")
    if moderation_comment:
        response_data["moderation_comment"] = moderation_comment

    # Добавим отладочное сообщение
    moderator_name = test_results.get("moderator")
    if moderator_name:
        response_data["moderator"] = moderator_name

    return Response(response_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([partial(HasPermission, perm='contenttypes.view_stat')])
def get_test_statistics(request):
    # Подзапрос для получения последней попытки каждого пользователя на каждом тесте
    last_attempt_subquery = TestAttempt.objects.filter(
        employee_id=OuterRef('employee_id'),
        test_id=OuterRef('test_id')
    ).order_by('-end_time').values('id')[:1]

    statistics = TestAttempt.objects.annotate(
        total_score=F('score'),
        max_score=F('test__max_score'),
        result=F('status'),
        experience=F('test__experience_points'),  # Добавляем опыт
        acoin=F('test__acoin_reward'),  # Добавляем Acoin
        is_last_attempt=Case(
            When(id=Subquery(last_attempt_subquery), then=True),
            default=False,
            output_field=BooleanField()
        ),  # Проверка на последнюю попытку
    ).values(
        'id',  # Нам нужен id для извлечения данных позже
        'test__id',
        'employee__first_name',
        'employee__last_name',
        'test__theme__name',
        'test__name',
        'total_score',
        'max_score',
        'result',
        'experience',  # Добавляем поле опыта
        'acoin',  # Добавляем поле Acoin
        'start_time',
        'end_time',
        'is_last_attempt'
    )

    # Обработка данных в Python: объединение имени и фамилии и добавление модератора
    statistics_list = []
    themes_set = set()  # Для хранения уникальных тем
    tests_set = set()
    employees_set = set()
    for stat in statistics:
        try:
            # Извлекаем full_name
            stat['full_name'] = f"{stat['employee__first_name']} {stat['employee__last_name']}"

            # Округляем до целого числа duration_seconds
            if stat['start_time'] and stat['end_time']:
                stat['duration_seconds'] = int((stat['end_time'] - stat['start_time']).total_seconds())
            else:
                stat['duration_seconds'] = None

            # Извлечение модератора из JSON-поля test_results
            test_attempt = TestAttempt.objects.get(id=stat['id'])
            if test_attempt.test_results:
                try:
                    test_results = json.loads(test_attempt.test_results)
                    stat['moderator'] = test_results.get('moderator', None)
                except json.JSONDecodeError as e:
                    stat['moderator'] = None
                    print(f"Ошибка разбора JSON для попытки {test_attempt.id}: {str(e)}")
            else:
                stat['moderator'] = None

            # Удаляем ненужные поля
            del stat['employee__first_name']
            del stat['employee__last_name']

            # Добавляем тему теста в set, чтобы не было дубликатов
            themes_set.add(stat['test__theme__name'])
            tests_set.add(stat['test__name'])
            employees_set.add(stat['full_name'])
            statistics_list.append(stat)
        except ObjectDoesNotExist as e:
            print(f"Ошибка: Не удалось найти TestAttempt с id {stat['id']}")
        except Exception as e:
            print(f"Неожиданная ошибка для попытки {stat['id']}: {str(e)}")

    # Преобразуем set тем в список
    themes_list = list(themes_set)
    tests_set = list(tests_set)
    employees_set = list(employees_set)
    return Response({
        'statistics': statistics_list,
        'themes': themes_list,  # Отдельный список уникальных тем
        'tests': tests_set,
        'employees': employees_set
    })



@api_view(['GET'])
def get_test_by_id(request, test_id):
    # Получаем тест по его ID или возвращаем ошибку 404, если тест не найден
    test = get_object_or_404(Test, id=test_id)

    # Сериализуем данные теста
    test_serializer = TestSerializer(test, context={'request': request})
    test_data = test_serializer.data

    # Получаем все вопросы и теорию для данного теста, отсортированные по позиции
    questions = TestQuestion.objects.filter(test=test).order_by('position')
    theories = Theory.objects.filter(test=test).order_by('position')

    # Создаем список для хранения блоков теста
    blocks = []

    # Добавляем данные о вопросах в список блоков
    for question in questions:
        question_data = TestQuestionSerializer(question, context={'request': request}).data
        del question_data['id']  # Удаляем поле "id"
        del question_data['test']  # Удаляем поле "test"
        answer_options = question_data.get('answer_options', [])
        for answer in answer_options:
            del answer['id']  # Удаляем поле "id" из каждого ответа
            del answer['question']
            del answer['file']
        block_data = {
            'type': 'question',
            'content': question_data
        }
        blocks.append(block_data)

    # Добавляем данные о теории в список блоков
    for theory in theories:
        theory_data = TheorySerializer(theory, context={'request': request}).data
        del theory_data['id']  # Удаляем поле "id"
        del theory_data['test']  # Удаляем поле "test"
        block_data = {
            'type': 'theory',
            'content': theory_data
        }
        blocks.append(block_data)

    # Сортируем блоки по позиции, если она есть
    sorted_blocks = sorted(blocks, key=lambda x: x['content'].get('position', 0))

    # Добавляем позицию вопроса к соответствующим блокам
    for block in sorted_blocks:
        block['content']['position'] = block['content'].get('position', 0)

    # Определение доступности теста
    employee = getattr(request, 'employee', request.user)
    test_available = True

    if not test.can_attempt_twice:
        last_test_attempt = TestAttempt.objects.filter(employee=employee, test=test, status=TestAttempt.PASSED).exists()
        if last_test_attempt:
            test_available = False

    # Возвращаем данные о тесте и его блоках
    response_data = {
        'test': test_data,
        'blocks': sorted_blocks,
        'test_available': test_available  # Добавляем статус доступности теста
    }
    return Response(response_data)




@permission_classes([IsAuthenticated])
class ThemesWithTestsView(APIView):
    def get(self, request, *args, **kwargs):
        employee = getattr(request, 'employee', request.user)
        employee_karma = getattr(employee, 'karma', 0)
        employee_experience = getattr(employee, 'experience', 0)

        themes = Theme.objects.all().order_by('name')
        themes_with_tests = []

        for theme in themes:
            tests = Test.objects.filter(theme=theme)
            tests_info = []

            for test in tests:
                created_at = test.created_at.strftime("%Y-%m-%dT%H:%M")
                test_attempt = TestAttempt.objects.filter(employee=employee, test=test).last()

                if test_attempt:
                    if test_attempt.test_results:
                        try:
                            test_results = json.loads(test_attempt.test_results)
                            total_score = test_results.get("Набранное количество баллов", 0)
                            max_score = test.max_score
                            answers_info = test_results.get("answers_info", [])
                            test_status = {
                                "status": test_attempt.status,
                                "total_score": test_attempt.score,
                                "max_score": max_score
                            }
                        except (json.JSONDecodeError, TypeError, KeyError):
                            test_status = None
                    else:
                        test_status = {"status": "Не начато", "total_score": 0, "max_score": 0}
                else:
                    test_status = {"status": "Не начато", "total_score": 0, "max_score": 0}

                has_sufficient_karma = employee_karma >= test.required_karma
                has_sufficient_experience = employee_experience >= test.min_experience

                remaining_days = None
                remaining_hours = None
                remaining_minutes = None
                test_available = has_sufficient_karma and has_sufficient_experience

                if test_attempt and test.retry_delay_days is not None:
                    end_time = test_attempt.end_time or timezone.now()
                    time_since_last_attempt = timezone.now() - end_time
                    remaining_time = timedelta(days=test.retry_delay_days) - time_since_last_attempt
                    if remaining_time.total_seconds() > 0:
                        remaining_days = remaining_time.days
                        test_available = False  # Обновляем test_available, если нужно ждать
                        if remaining_days >= 1:
                            remaining_hours = remaining_time.seconds // 3600
                        else:
                            remaining_hours, remaining_seconds = divmod(remaining_time.seconds, 3600)
                            remaining_minutes = remaining_seconds // 60

                # Если тест одноразовый и уже был пройден
                if not test.can_attempt_twice and TestAttempt.objects.filter(employee=employee, test=test, status=TestAttempt.PASSED).exists():
                    test_available = False

                test_info = {
                    'test': test.id,
                    'name': test.name,
                    'required_karma': test.required_karma,
                    'min_exp': test.min_experience,
                    'achievement': test.achievement.name if test.achievement else None,
                    'created_at': created_at,
                    'author': test.author.name if test.author else None,
                    'status': test_status,
                    'has_sufficient_karma': has_sufficient_karma,
                    'has_sufficient_experience': has_sufficient_experience,
                    'test_available': test_available,
                    'remaining_time': f"{remaining_days} {remaining_hours}"
                }

                tests_info.append(test_info)

            theme_with_tests = {
                'theme': theme.name,
                'theme_id': theme.id,
                'tests': tests_info
            }
            themes_with_tests.append(theme_with_tests)

        return Response(themes_with_tests)

@api_view(['GET'])
def get_question(request, question_id):
    question = get_object_or_404(TestQuestion, id=question_id)
    serializer = TestQuestionSerializer(question)
    return Response(serializer.data)

class PasswordManagementView(APIView):
    def post(self, request, user_id=None):
        # В зависимости от наличия user_id, выбираем нужный метод
        if user_id:
            return self.admin_change_password(request, user_id)
        else:
            return self.user_change_password(request)

    @staticmethod
    def validate_password_policy(password, policy):
        """
        Функция для проверки пароля на соответствие политике паролей.
        """
        if len(password) < policy.min_length:
            raise ValidationError(f"Пароль должен содержать минимум {policy.min_length} символов.")
        if len(password) > policy.max_length:
            raise ValidationError(f"Пароль должен содержать не более {policy.max_length} символов.")
        if sum(1 for c in password if c.isupper()) < policy.min_uppercase:
            raise ValidationError(f"Пароль должен содержать минимум {policy.min_uppercase} заглавных букв.")
        if sum(1 for c in password if c.islower()) < policy.min_lowercase:
            raise ValidationError(f"Пароль должен содержать минимум {policy.min_lowercase} строчных букв.")
        if sum(1 for c in password if c.isdigit()) < policy.min_digits:
            raise ValidationError(f"Пароль должен содержать минимум {policy.min_digits} цифр.")
        if sum(1 for c in password if c in policy.allowed_symbols) < policy.min_symbols:
            raise ValidationError(
                f"Пароль должен содержать минимум {policy.min_symbols} символов из списка допустимых.")
        if policy.no_spaces and ' ' in password:  # Добавлена явная проверка на пробелы
            raise ValidationError("Пароль не должен содержать пробелов.")

    def admin_change_password(self, request, user_id):
        """
        Метод для смены пароля администратора.
        """
        try:
            # Проверка прав администратора
            self.permission_classes = [IsAdminUser]

            employee = get_object_or_404(Employee, id=user_id)
            password_policy = PasswordPolicy.objects.first()

            # Получаем новый пароль из запроса
            new_password = request.data.get('new_password', None)
            ignore_policy = request.data.get('ignore_policy', False)  # Флаг для игнорирования политики

            if new_password:
                if not ignore_policy:
                    # Проверка вручную введенного пароля на соответствие политике
                    self.validate_password_policy(new_password, password_policy)
                # Если флаг ignore_policy установлен, пропускаем проверку политики пароля
            else:
                # Если новый пароль не предоставлен, генерируем случайный
                new_password = get_random_string(length=password_policy.min_length)

                # Проверка случайно сгенерированного пароля на соответствие политике
                self.validate_password_policy(new_password, password_policy)

            # Хеширование и сохранение пароля
            employee.password = make_password(new_password)
            employee.save()

            # Отправка нового пароля на email
            subject = 'Ваш новый пароль'
            message = f'Здравствуйте, {employee.first_name}!\n\nВаш новый пароль: {new_password}\n'
            email = EmailMessage(subject, message, to=[employee.email])
            email.send()

            return Response({"message": "Пароль успешно изменен и отправлен на email.", "password": new_password},
                            status=status.HTTP_200_OK)

        except ValidationError as e:
            return Response({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def user_change_password(self, request):
        """
        Метод для смены пароля пользователя.
        """
        try:
            user = request.user
            old_password = request.data.get('old_password')
            new_password = request.data.get('new_password')

            if not old_password or not new_password:
                return Response({"message": "Оба поля 'старый пароль' и 'новый пароль' должны быть заполнены."},
                                status=status.HTTP_400_BAD_REQUEST)

            if not check_password(old_password, user.password):
                return Response({"message": "Старый пароль неверен."}, status=status.HTTP_400_BAD_REQUEST)

            password_policy = PasswordPolicy.objects.first()

            # Проверка нового пароля на соответствие политике паролей
            self.validate_password_policy(new_password, password_policy)

            # Хеширование и сохранение нового пароля
            user.password = make_password(new_password)
            user.save()

            return Response({"message": "Пароль успешно изменен."}, status=status.HTTP_200_OK)

        except ValidationError as e:
            return Response({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PasswordPolicyViewSet(BasePermissionViewSet):
    queryset = PasswordPolicy.objects.all()
    serializer_class = PasswordPolicySerializer
    def generate_password_policy_description(self, policy):
        """
        Функция для генерации краткого описания политики пароля.
        Возвращает список описаний.
        """
        descriptions = []

        if policy.min_uppercase > 0:
            description = f"{policy.min_uppercase} заглавная" if policy.min_uppercase == 1 else f"{policy.min_uppercase} заглавных"
            regex = f"(?=(.*[A-Z]){{{policy.min_uppercase},}})"
            descriptions.append({"description": description, "regex": regex})

        if policy.min_lowercase > 0:
            description = f"{policy.min_lowercase} строчная" if policy.min_lowercase == 1 else f"{policy.min_lowercase} строчных"
            regex = f"(?=(.*[a-z]){{{policy.min_lowercase},}})"
            descriptions.append({"description": description, "regex": regex})

        if policy.min_digits > 0:
            description = f"{policy.min_digits} цифра" if policy.min_digits == 1 else f"{policy.min_digits} цифр"
            regex = f"(?=(.*[0-9]){{{policy.min_digits},}})"
            descriptions.append({"description": description, "regex": regex})

        if policy.min_symbols > 0:
            description = f"{policy.min_symbols} спец. символ" if policy.min_symbols == 1 else f"{policy.min_symbols} спец. символов"
            allowed_symbols_escaped = re.escape(policy.allowed_symbols)
            regex = f"(?=(.*[{allowed_symbols_escaped}]){{{policy.min_symbols},}})"
            descriptions.append({"description": description, "regex": regex})

        if policy.no_spaces:
            description = "Без пробелов"
            regex = r"(?!.*\s)"
            descriptions.append({"description": description, "regex": regex})

        if policy.min_length > 0:
            description = f"{policy.min_length}-{policy.max_length} символов"
            regex = f".{{{policy.min_length},{policy.max_length}}}"
            descriptions.append({"description": description, "regex": regex})

        return descriptions

    @action(detail=False, methods=['get'])
    def get_password_policy_regex(self, request):
        """
        API-запрос для получения частей регулярного выражения, соответствующего политике паролей, с описанием.
        """
        try:
            policy = PasswordPolicy.objects.first()  # Предполагается, что политика одна

            if not policy:
                return Response({"error": "Политика паролей не найдена."}, status=404)

            # Генерация краткого описания политики пароля с регулярными выражениями
            descriptions = self.generate_password_policy_description(policy)

            return Response({"descriptions": descriptions}, status=200)
        except Exception as e:
            return Response({"error": str(e)}, status=400)

    @action(detail=False, methods=['get'])
    def get_policy(self, request):
        """
        API-запрос для получения текущей политики паролей.
        """
        policy = PasswordPolicy.objects.first()
        if not policy:
            return Response({"error": "Политика паролей не найдена."}, status=404)

        # Используем обновленный сериализатор для вывода
        serializer = PasswordPolicySerializer(policy)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def update_policy(self, request):
        """
        API-запрос для обновления текущей политики паролей.
        """
        policy = PasswordPolicy.objects.first()
        if not policy:
            return Response({"error": "Политика паролей не найдена."}, status=404)

        serializer = PasswordPolicySerializer(policy, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
@api_view(['POST'])
@permission_classes([partial(HasPermission, perm='main.add_request')])
def create_request(request):
    serializer = RequestSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([IsAdmin])
class ThemeDeleteAPIView(APIView):
    def delete(self, request, theme_id):
        try:
            theme = Theme.objects.get(id=theme_id)
        except Theme.DoesNotExist:
            return Response({"message": "Theme not found"}, status=status.HTTP_404_NOT_FOUND)

        theme.delete()
        return Response({"message": "Theme deleted successfully"}, status=status.HTTP_204_NO_CONTENT)
@permission_classes([IsAdmin])
@api_view(['PATCH'])
def update_theme_name(request, theme_id):
    try:
        # Получаем тему по идентификатору
        theme = Theme.objects.get(id=theme_id)
    except Theme.DoesNotExist:
        return Response({"message": "Theme not found"}, status=status.HTTP_404_NOT_FOUND)

    # Получаем новое название из запроса
    new_name = request.data.get('name')
    if not new_name:
        return Response({"message": "New name is required"}, status=status.HTTP_400_BAD_REQUEST)

    # Обновляем название темы
    theme.name = new_name
    theme.save()

    return Response({"message": "Theme name updated successfully"}, status=status.HTTP_200_OK)

@permission_classes([IsAdmin])
@api_view(['DELETE'])
def delete_test_attempt(request, attempt_id):
    try:
        # Находим попытку прохождения теста по её ID
        test_attempt = TestAttempt.objects.get(id=attempt_id)
    except TestAttempt.DoesNotExist:
        return Response({"message": "Test attempt not found"}, status=status.HTTP_404_NOT_FOUND)

    # Удаляем попытку прохождения теста
    test_attempt.delete()

    return Response({"message": "Test attempt deleted successfully"}, status=status.HTTP_200_OK)
@permission_classes([IsAdmin])
@api_view(['POST'])
def create_achievement(request):
    if request.method == 'POST':
        achievement_data = request.data
        serializer = AchievementSerializer(data=achievement_data)

        if serializer.is_valid():
            achievement_type = achievement_data.get('type')

            if achievement_type == 'Requests':
                required_fields = ['required_count', 'reward_experience', 'reward_currency', 'request_type']
                for field in required_fields:
                    if field not in achievement_data:
                        return Response(
                            {"error": f"Field '{field}' is required for achievements based on number of requests."},
                            status=status.HTTP_400_BAD_REQUEST)

            elif achievement_type == 'Test':
                try:
                    test_classification = Classifications.objects.get(name="Test")
                    serializer.validated_data['request_type'] = test_classification
                    serializer.validated_data['required_count'] = 0
                except Classifications.DoesNotExist:
                    return Response(
                        {"error": "No classification with name 'Test' found."},
                        status=status.HTTP_400_BAD_REQUEST)

            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CreateClassificationAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    authentication_classes = [TokenAuthentication]

    def post(self, request):
        name = request.data.get('name')

        if name:
            try:
                existing_classification = Classifications.objects.get(name=name)
                return Response({'error': 'Classification with this name already exists'},
                                status=status.HTTP_400_BAD_REQUEST)
            except Classifications.DoesNotExist:
                classification_data = {'name': name}
                serializer = ClassificationSerializer(data=classification_data)
                if serializer.is_valid():
                    serializer.save()
                    return Response(serializer.data, status=status.HTTP_201_CREATED)
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'error': 'Name field is required'}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def create_acoin_transaction(request):
    if request.method == 'POST':
        serializer = AcoinTransactionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
@api_view(['GET'])
def get_answer(request, answer_id):
    answer = get_object_or_404(AnswerOption, id=answer_id)
    serializer = AnswerOptionSerializer(answer)
    return Response(serializer.data)

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def create_test(request):
    print(f"Incoming request data: {request.data}")

    if request.content_type == 'application/json':
        blocks_data = request.data.get('blocks', [])
    elif 'multipart/form-data' in request.content_type:
        try:
            blocks_data = json.loads(request.data.get('blocks', '[]'))
        except json.JSONDecodeError:
            return Response({'error': 'Invalid JSON format for blocks'}, status=status.HTTP_400_BAD_REQUEST)
    else:
        return Response({'error': 'Unsupported media type'}, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

    if not isinstance(blocks_data, list):
        return Response({'error': 'Blocks should be a list'}, status=status.HTTP_400_BAD_REQUEST)

    if not any(isinstance(block, dict) and block.get('type') == 'question' for block in blocks_data):
        return Response({'error': 'Test should contain at least one question'}, status=status.HTTP_400_BAD_REQUEST)

    # Обработка изображения для теста
    mutable_data = request.data.copy()
    if 'image' in request.data:
        base64_image = request.data['image']
        if base64_image:
            try:
                filename = f"test_{request.data.get('name', 'unknown')}"
                mutable_data['image'] = save_base64_image(base64_image, filename)
            except ValueError as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            mutable_data['image'] = None
    else:
        mutable_data.pop('image', None)

    test_serializer = TestSerializer(data=mutable_data)
    if not test_serializer.is_valid():
        return Response(test_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    test = test_serializer.save()

    created_questions = []
    created_theories = []
    created_answers = []

    position = 1

    for block_data in blocks_data:
        if not isinstance(block_data, dict) or 'type' not in block_data or 'content' not in block_data:
            return Response({'error': 'Invalid block format'}, status=status.HTTP_400_BAD_REQUEST)

        block_data['content']['test'] = test.id

        if block_data['type'] == 'question':
            if 'image' in block_data['content']:
                base64_image = block_data['content']['image']
                if base64_image:
                    try:
                        filename = f"question_{position}"
                        block_data['content']['image'] = save_base64_image(base64_image, filename)
                    except ValueError as e:
                        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
                else:
                    block_data['content']['image'] = None
            else:
                block_data['content'].pop('image', None)

            serializer_class = TestQuestionSerializer
            created_list = created_questions
        elif block_data['type'] == 'theory':
            if 'image' in block_data['content']:
                base64_image = block_data['content']['image']
                if base64_image:
                    try:
                        filename = f"theory_{position}"
                        block_data['content']['image'] = save_base64_image(base64_image, filename)
                    except ValueError as e:
                        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
                else:
                    block_data['content']['image'] = None
            else:
                block_data['content'].pop('image', None)

            serializer_class = TheorySerializer
            created_list = created_theories
        else:
            return Response({'error': 'Invalid block type'}, status=status.HTTP_400_BAD_REQUEST)

        block_serializer = serializer_class(data=block_data['content'])
        if not block_serializer.is_valid():
            return Response(block_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        block = block_serializer.save(position=position)
        created_list.append(block_serializer.data)

        if block_data['type'] == 'question':
            answers_data = block_data['content'].get('answer_options', [])

            for answer_data in answers_data:
                answer_data['question'] = block.id

                answer_serializer = AnswerOptionSerializer(data=answer_data)
                if not answer_serializer.is_valid():
                    return Response(answer_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

                answer = answer_serializer.save()
                created_answers.append(answer_serializer.data)

        position += 1

    response_data = {
        'test_id': test.id,
        'created_questions': created_questions,
        'created_theories': created_theories,
        'created_answers': created_answers
    }

    return Response(response_data, status=status.HTTP_201_CREATED)

def save_base64_image(base64_image, filename_prefix):
    try:
        format, imgstr = base64_image.split(';base64,')
        ext = format.split('/')[-1].lower()
        if ext not in ['jpeg', 'jpg', 'png']:
            raise ValueError('Unsupported image format')

        img_data = base64.b64decode(imgstr)
        unique_filename = f"{filename_prefix}_{uuid.uuid4()}.{ext}"

        return ContentFile(img_data, name=unique_filename)
    except Exception as e:
        raise ValueError(f'Error saving image: {str(e)}')


def get_questions_with_explanations(request, test_id):
    # Получаем объект теста по его идентификатору
    test = get_object_or_404(Test, id=test_id)

    # Получаем все вопросы для данного теста
    questions = TestQuestion.objects.filter(test=test)

    # Список для хранения данных о вопросах и пояснениях
    questions_data = []

    # Получаем данные о каждом вопросе и его пояснении
    for index, question in enumerate(questions, start=1):
        question_data = {
            'question_number': index,  # Номер вопроса в тесте
            'question_text': question.question_text,  # Текст вопроса
            'explanation': question.explanation  # Пояснение к вопросу
        }
        questions_data.append(question_data)

    # Преобразуем данные в формат JSON
    data_json = json.dumps({'questions': questions_data}, ensure_ascii=False)

    # Возвращаем ответ с данными в формате JSON
    return HttpResponse(data_json, content_type='application/json; charset=utf-8')


@api_view(['GET'])
def test_status(request, employee_id, test_id):
    try:
        employee = Employee.objects.get(id=employee_id)
        test = Test.objects.get(id=test_id)
    except (Employee.DoesNotExist, Test.DoesNotExist):
        return Response({"message": "Employee or Test not found"}, status=status.HTTP_404_NOT_FOUND)

    test_attempt = TestAttempt.objects.filter(employee=employee, test=test).first()

    if not test_attempt:
        return Response({"message": "Test attempt not found"}, status=status.HTTP_404_NOT_FOUND)

    # Десериализуем строку JSON в объект Python
    test_results = json.loads(test_attempt.test_results)

    total_score = test_results.get("Набранное количество баллов", 0)
    max_score = test.max_score
    answers_info = test_results.get("answers_info", [])

    # Подсчет количества правильных ответов
    correct_answers_count = sum(1 for answer_info in answers_info if answer_info["is_correct"])

    # Формирование сообщения в зависимости от статуса теста
    if test_attempt.status == TestAttempt.PASSED:
        status_message = "Test Passed."
        correct_answers_info = f"{correct_answers_count}/{len(answers_info)}"
    elif test_attempt.status == TestAttempt.FAILED:
        status_message = "Test Failed."
        correct_answers_info = f"{correct_answers_count}/{len(answers_info)}"
    else:
        status_message = "Test in Progress"
        correct_answers_info = ""

    response_data = {
        "status": status_message,
        "total_score": total_score,
        "max_score": max_score
    }

    return Response(response_data, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsModeratorOrAdmin])
def feedbacks_pending_moderation(request):
    feedbacks = Feedback.objects.filter(status='pending')
    serializer = FeedbackSerializer(feedbacks, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsModeratorOrAdmin])
def test_attempt_moderation_list(request):
    # Получаем последние попытки прохождения тестов на модерации для каждого пользователя и теста
    latest_attempts = TestAttempt.objects.filter(status=TestAttempt.MODERATION) \
        .values('employee', 'test') \
        .annotate(max_end_time=Max('end_time')) \
        .distinct()

    # Получаем соответствующие попытки прохождения тестов
    test_attempts = TestAttempt.objects.filter(
        status=TestAttempt.MODERATION,
        end_time__in=[attempt['max_end_time'] for attempt in latest_attempts]
    )

    # Сортируем попытки прохождения тестов по темам тестов
    sorted_attempts = sorted(test_attempts, key=lambda x: x.test.theme.name)

    # Группируем попытки прохождения тестов по темам
    grouped_by_theme = {}
    for attempt in sorted_attempts:
        theme_name = attempt.test.theme.name
        if theme_name not in grouped_by_theme:
            grouped_by_theme[theme_name] = []
        grouped_by_theme[theme_name].append(attempt)

    # Формируем ответные данные
    response_data = []
    for theme, attempts in grouped_by_theme.items():
        serializer = TestAttemptModerationSerializer(attempts, many=True)
        response_data.append({
            'theme': theme,
            'test_attempts': serializer.data
        })

    return Response(response_data, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsModeratorOrAdmin])
def moderate_test_attempt(request, test_attempt_id):
    try:
        test_attempt = TestAttempt.objects.get(id=test_attempt_id)
    except TestAttempt.DoesNotExist:
        return Response({"message": "Test Attempt not found"}, status=status.HTTP_404_NOT_FOUND)

    # Получаем текущего пользователя (модератора)
    moderator = request.employee
    print(f"Moderator: {moderator.username} is moderating test attempt {test_attempt_id}")

    if 'moderated_questions' not in request.data:
        return Response({"message": "Moderated questions are required"}, status=status.HTTP_400_BAD_REQUEST)

    moderated_questions = request.data['moderated_questions']

    # Преобразуем строку test_results в словарь
    try:
        test_results = json.loads(test_attempt.test_results)
    except json.JSONDecodeError:
        return Response({"message": "Invalid test_results format"}, status=status.HTTP_400_BAD_REQUEST)

    answers_info = test_results.get('answers_info', [])

    if test_attempt.status != TestAttempt.MODERATION:
        return Response({"message": "Test attempt is not on moderation"}, status=status.HTTP_400_BAD_REQUEST)

    for moderated_question in moderated_questions:
        question_number = moderated_question.get('question_number')
        moderation_score = moderated_question.get('moderation_score')
        moderation_comment = moderated_question.get('moderation_comment', '')

        if moderation_score is None:
            return Response({"message": "Moderation score is required for each question"}, status=status.HTTP_400_BAD_REQUEST)

        if question_number < 1 or question_number > len(answers_info):
            return Response({"message": "Invalid question number"}, status=status.HTTP_400_BAD_REQUEST)

        question_to_moderate = answers_info[question_number - 1]

        if 'type' not in question_to_moderate or question_to_moderate['type'] != 'text':
            return Response({"message": "You can only moderate questions with type 'text'"}, status=status.HTTP_400_BAD_REQUEST)

        max_question_score = question_to_moderate.get('max_question_score', 0)

        if moderation_score > max_question_score:
            return Response({"message": f"Moderation score exceeds the maximum allowed score ({max_question_score})"}, status=status.HTTP_400_BAD_REQUEST)

        question_to_moderate['question_score'] = moderation_score
        question_to_moderate['moderation_comment'] = moderation_comment

        if moderation_score == max_question_score:
            question_to_moderate['is_correct'] = True
        elif moderation_score > 0:
            question_to_moderate['is_correct'] = False
            question_to_moderate['is_partially_true'] = True
        else:
            question_to_moderate['is_correct'] = False
            question_to_moderate['is_partially_true'] = False

    test_results['answers_info'] = answers_info

    test_results['moderator'] = f"{moderator.first_name} {moderator.last_name}"
    test_attempt.test_results = json.dumps(test_results)

    total_score = sum(question.get('question_score', 0) for question in answers_info)
    test_attempt.score = round(total_score, 1)

    if total_score >= test_attempt.test.passing_score:
        test_attempt.status = TestAttempt.PASSED
    else:
        test_attempt.status = TestAttempt.FAILED

    test_attempt.end_time = timezone.now()
    test_attempt.save()

    # Начисление опыта модератору за модерацию теста
    try:
        experience_multiplier = KarmaSettings.objects.get(operation_type="TEST_MODERATION")
        experience_awarded = experience_multiplier.experience_change
    except KarmaSettings.DoesNotExist:
        experience_awarded = 10  # Дефолтное значение опыта, если настройка не найдена

    moderator.add_experience(experience_awarded, source=f'За модерацию теста {test_attempt.test.name}')
    moderator.save()

    # Начисление опыта сотруднику за прохождение теста
    test_employee = test_attempt.employee
    experience_for_employee = test_attempt.test.experience_points
    if test_attempt.status == TestAttempt.PASSED:
        test_employee.add_experience(experience_for_employee, source=f'За прохождение теста {test_attempt.test.name}')

    test_employee.save()

    response_data = {
        "score": test_attempt.score,
        "message": "Test moderated successfully",
        "status": test_attempt.status,
        "moderator": f"{moderator.first_name} {moderator.last_name}",
        "experience_awarded_to_moderator": experience_awarded,
        "experience_awarded_to_employee": experience_for_employee
    }

    return Response(response_data, status=status.HTTP_200_OK)



@api_view(['GET'])
def required_tests_chain(request, employee_id, test_id):
    try:
        employee = Employee.objects.get(id=employee_id)
        test = Test.objects.get(id=test_id)
    except (Employee.DoesNotExist, Test.DoesNotExist):
        return Response({"message": "Employee or Test not found"}, status=status.HTTP_404_NOT_FOUND)

    required_tests = []  # Список для хранения цепочки тестов
    tests_not_passed = []  # Список для хранения тестов, которые не прошел сотрудник

    # Начинаем с текущего теста и движемся по цепочке required_test
    current_test = test
    while current_test.required_test:
        required_tests.insert(0, current_test.required_test)  # Добавляем предыдущий тест в начало списка
        current_test = current_test.required_test

    # Проверяем, прошел ли сотрудник каждый из необходимых тестов
    for req_test in required_tests:
        if not TestAttempt.objects.filter(employee=employee, test=req_test, status=TestAttempt.PASSED).exists():
            tests_not_passed.append(req_test.id)

    # Формируем список идентификаторов тестов в цепочке
    tests_chain_ids = [test.id for test in required_tests]

    if not tests_chain_ids:
        return Response({"message": "No required tests found for this test"}, status=status.HTTP_200_OK)

    response_data = {}

    if tests_not_passed:
        response_data["tests_not_passed"] = tests_not_passed

    return Response(response_data, status=status.HTTP_200_OK)


class StartTestView(EmployeeAPIView):

    def post(self, request, test_id, *args, **kwargs):
        employee = request.employee

        try:
            test = Test.objects.get(id=test_id)
        except Test.DoesNotExist:
            return Response({"message": "Test not found"}, status=status.HTTP_404_NOT_FOUND)

        required_test = test.required_test
        if required_test:
            if not TestAttempt.objects.filter(employee=employee, test=required_test, status=TestAttempt.PASSED).exists():
                return Response({"message": f"You must pass test {required_test.id} before starting this test"},
                                status=status.HTTP_400_BAD_REQUEST)

        old_attempts = TestAttempt.objects.filter(
            employee=employee, test=test, status__in=[TestAttempt.IN_PROGRESS, TestAttempt.NOT_STARTED]
        )

        if old_attempts.exists():
            old_attempts.delete()

        test_attempt = TestAttempt.objects.create(
            employee=employee,
            test=test,
            status=TestAttempt.IN_PROGRESS
        )

        return Response({"test_attempt_id": test_attempt.id}, status=status.HTTP_201_CREATED)


class CompleteTestView(EmployeeAPIView):

    def post(self, request, test_id, *args, **kwargs):
        employee = request.employee

        try:
            test = Test.objects.get(id=test_id)
        except Test.DoesNotExist:
            return Response({"message": "Test not found"}, status=status.HTTP_404_NOT_FOUND)

        test_attempt = TestAttempt.objects.filter(employee=employee, test=test, status=TestAttempt.IN_PROGRESS).order_by('-start_time').last()

        if not test_attempt:
            return Response({"message": "Test attempt not found"}, status=status.HTTP_404_NOT_FOUND)

        questions = TestQuestion.objects.filter(test=test)
        total_score = Decimal('0.0')
        max_score = Decimal('0.0')
        answers_info = []

        for question_number, question in enumerate(questions, start=1):
            submitted_text_answer = ""
            question_text = question.question_text
            answer_options = [
                {'option_number': index + 1, 'option_text': option.option_text, 'is_correct': option.is_correct} for
                index, option in enumerate(question.answer_options.all())]
            max_score += Decimal(str(question.points))

            answer_key = str(question_number)
            if answer_key in request.data:
                submitted_answer = request.data[answer_key]

                is_correct = False

                if question.question_type == 'single':
                    submitted_answer_number = int(submitted_answer)
                    submitted_answer_option = answer_options[submitted_answer_number - 1]
                    is_correct = submitted_answer_option['is_correct']
                    if is_correct:
                        total_score += Decimal(str(question.points))
                        question_score = Decimal(str(question.points))
                    else:
                        question_score = Decimal('0.0')
                elif question.question_type == 'text':
                    submitted_text_answer = submitted_answer
                    question_score = Decimal('0.0')
                elif question.question_type == 'multiple':
                    if isinstance(submitted_answer, int):
                        submitted_answer = [submitted_answer]
                    submitted_answer_numbers = [int(answer) for answer in submitted_answer]
                    correct_option_numbers = [index + 1 for index, option in enumerate(answer_options) if option['is_correct']]

                    selected_correct_answers = sum(1 for answer in submitted_answer_numbers if answer in correct_option_numbers)
                    selected_incorrect_answers = sum(1 for answer in submitted_answer_numbers if answer not in correct_option_numbers)

                    question_score_per_correct_answer = Decimal(str(question.points)) / Decimal(len(correct_option_numbers))
                    question_score_per_incorrect_answer = Decimal(str(question.points)) / Decimal(len(correct_option_numbers))

                    question_score = (selected_correct_answers * question_score_per_correct_answer) - (selected_incorrect_answers * question_score_per_incorrect_answer)

                    if question_score < 0:
                        question_score = Decimal('0.0')

                    if selected_correct_answers == len(correct_option_numbers) and selected_incorrect_answers == 0:
                        is_correct = True

                    total_score += question_score

                question_score = question_score.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)

                answer_info = {
                    "question_text": question_text,
                    "type": question.question_type,
                    "is_correct": is_correct,
                    "question_score": float(question_score),
                    "answer_options": [],
                    "explanation": question.explanation
                }
                if question.question_type == 'text':
                    answer_info['text_answer'] = submitted_text_answer
                    answer_info['max_question_score'] = float(question.points)
                else:
                    for option in answer_options:
                        option_info = {
                            "option_number": option["option_number"],
                            "option_text": option["option_text"],
                            "submitted_answer": option["option_number"] in submitted_answer_numbers if isinstance(submitted_answer, list) else option["option_number"] == int(submitted_answer),
                            "correct_options": option["is_correct"]
                        }
                        answer_info["answer_options"].append(option_info)
                answers_info.append(answer_info)

        total_score = total_score.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)

        test_attempt.test_results = json.dumps({
            "Набранное количество баллов": float(total_score),
            "Максимальное количество баллов": float(max_score),
            "answers_info": answers_info
        }, ensure_ascii=False)
        test_attempt.end_time = timezone.now()
        test_attempt.score = total_score  # Обновляем поле score
        test_attempt.save()

        has_text_questions = TestQuestion.objects.filter(test=test, question_type='text').exists()

        if total_score >= Decimal(str(test.passing_score)):
            test_attempt.status = TestAttempt.PASSED
            # Присваиваем опыт за прохождение теста
            employee.add_experience(Test.experience_points, source=f"За прохождение теста {test.name}")
            print(f"Added {Test.experience_points} experience points to {employee.username} for passing test {test_id}")
        elif has_text_questions:
            test_attempt.status = TestAttempt.MODERATION
        else:
            test_attempt.status = TestAttempt.FAILED

        test_attempt.save()

        response_data = {
            "status": test_attempt.status,
            "test_attempt_id": test_attempt.id
        }
        return Response(response_data, status=status.HTTP_200_OK)




@api_view(['GET'])
def top_participants(request):
    test_id = request.query_params.get('test_id')

    if test_id:
        # Если test_id указан, находим все попытки для каждого сотрудника по этому тесту
        test_attempts = TestAttempt.objects.filter(test_id=test_id).values(
            'employee_id', 'employee__first_name', 'employee__last_name'
        ).annotate(
            total_score=Sum('score'),
            total_attempts=Count('id'),
            average_score=ExpressionWrapper(
                Sum('score') / Count('id'),
                output_field=FloatField()
            ),
            best_score=Max('score')
        ).order_by('-best_score')

        top_participants = [
            {
                'employee_name': f"{item['employee__first_name']} {item['employee__last_name']}",
                'total_score': item['total_score'],
                'total_attempts': item['total_attempts'],
                'average_score': round(item['average_score'], 2) if item['average_score'] is not None else None,
                'best_score': item['best_score']
            }
            for item in test_attempts
        ]
    else:
        # Если test_id не указан, находим средний score для каждого сотрудника по всем тестам
        avg_scores = TestAttempt.objects.values(
            'employee_id', 'employee__first_name', 'employee__last_name'
        ).annotate(
            total_score=Sum('score'),
            total_attempts=Count('id'),
            average_score=ExpressionWrapper(
                Sum('score') / Count('id'),
                output_field=FloatField()
            )
        ).order_by('-average_score')

        top_participants = [
            {
                'employee_name': f"{item['employee__first_name']} {item['employee__last_name']}",
                'total_score': item['total_score'],
                'total_attempts': item['total_attempts'],
                'average_score': round(item['average_score'], 2) if item['average_score'] is not None else None
            }
            for item in avg_scores
        ]

    return Response(top_participants, status=status.HTTP_200_OK)
class StatisticsAPIView(APIView):
    def get(self, request):
        # Получаем всех сотрудников
        employees = Employee.objects.all()

        # Список для хранения статистики по каждому сотруднику
        employees_statistics = []

        # Обходим каждого сотрудника
        for employee in employees:
            # Получаем количество заработанных валют текущего сотрудника
            total_acoins = Acoin.objects.filter(employee=employee).aggregate(total_acoins=Sum('amount'))['total_acoins'] or 0

            # Получаем количество заработанного опыта текущего сотрудника
            total_experience = employee.experience

            # Получаем количество заработанных достижений текущего сотрудника
            total_achievements = EmployeeAchievement.objects.filter(employee=employee).count()

            # Добавляем информацию о текущем сотруднике в список
            employee_info = {
                "employee_id": employee.id,
                "total_acoins": total_acoins,
                "total_experience": total_experience,
                "total_achievements": total_achievements
            }
            employees_statistics.append(employee_info)

        # Возвращаем информацию по каждому сотруднику
        return JsonResponse(employees_statistics, safe=False)

@permission_classes([IsAdmin])
class QuestionErrorsStatistics(APIView):
    def get(self, request):
        # Создаем словари для хранения информации о частоте ошибок и общего числа ответов
        error_counter = Counter()
        total_answers_counter = Counter()

        # Обходим все попытки прохождения тестов
        for attempt in TestAttempt.objects.all():
            # Получаем результаты теста для текущей попытки
            test_results = attempt.test_results
            if isinstance(test_results, str):
                # Если test_results - строка, пытаемся преобразовать ее в словарь
                try:
                    results_dict = json.loads(test_results)
                    for answer_info in results_dict.get("answers_info", []):
                        question_text = answer_info.get("question_text")
                        test_id = attempt.test_id
                        question_id = f"{question_text}_{test_id}"
                        # Увеличиваем счетчик общего числа ответов только один раз для каждого вопроса
                        total_answers_counter[question_id] += 1
                        # Проверяем, является ли ответ неправильным
                        if not answer_info["is_correct"]:
                            error_counter[question_id] += 1
                except ValueError:
                    # Если не удалось преобразовать строку в JSON, пропускаем эту попытку
                    pass

        # Формируем список вопросов, по которым чаще всего ошибаются
        most_common_errors = [
            {
                "question_id": qid.split('_')[0],
                "test_id": qid.split('_')[1],
                "question_text": qid.split('_')[0],
                "total_answers": total_answers_counter[qid],
                "count": count,
                "ratio": round(count / total_answers_counter[qid] * 100, 1) if total_answers_counter[qid] != 0 else 0
            }
            for qid, count in error_counter.items()
        ]

        # Сортируем список по соотношению неверных ответов к общему количеству ответов
        most_common_errors = sorted(most_common_errors, key=lambda x: x["ratio"], reverse=True)

        return Response({
            "most_common": most_common_errors
        })
class PositionListView(APIView):
    permission_classes = [IsAdmin]  # Укажите необходимые разрешения

    def get(self, request, *args, **kwargs):
        positions = [position[0] for position in Employee.POSITION_CHOICES]
        return Response({'positions': positions}, status=200)

@permission_classes([IsAdmin])
class QuestionCorrectStatistics(APIView):
    def get(self, request):
        # Создаем словари для хранения информации о частоте правильных ответов и общего количества ответов
        correct_counter = Counter()
        total_answers_counter = Counter()

        # Обходим все попытки прохождения тестов
        for attempt in TestAttempt.objects.all():
            # Получаем результаты теста для текущей попытки
            test_results = attempt.test_results
            if isinstance(test_results, str):
                # Если test_results - строка, пытаемся преобразовать ее в словарь
                try:
                    results_dict = json.loads(test_results)
                    for answer_info in results_dict.get("answers_info", []):
                        question_text = answer_info.get("question_text")
                        test_id = attempt.test_id
                        question_id = f"{question_text}_{test_id}"
                        # Увеличиваем счетчик общего числа ответов только один раз для каждого вопроса
                        total_answers_counter[question_id] += 1
                        # Проверяем, является ли ответ правильным
                        if answer_info["is_correct"]:
                            correct_counter[question_id] += 1
                except ValueError:
                    # Если не удалось преобразовать строку в JSON, пропускаем эту попытку
                    pass

        # Формируем список вопросов, по которым чаще всего отвечают правильно
        most_common_correct = [
            {
                "question_id": qid.split('_')[0],
                "test_id": qid.split('_')[1],
                "question_text": qid.split('_')[0],
                "total_answers": total_answers_counter[qid],
                "count": count,
                "ratio": round(count / total_answers_counter[qid] * 100, 1) if total_answers_counter[qid] != 0 else 0
            }
            for qid, count in correct_counter.items()
        ]

        # Сортируем список по соотношению правильных ответов к общему количеству ответов
        most_common_correct = sorted(most_common_correct, key=lambda x: x["ratio"], reverse=True)

        return Response({
            "most_common": most_common_correct
        })
class TestStatisticsAPIView(APIView):
    def get(self, request):
        # Определите начальную и конечную даты для анализа
        start_date = timezone.now() - timezone.timedelta(days=100)  # Например, за последние 30 дней
        end_date = timezone.now()

        # Получите успешные попытки прохождения теста за указанный период
        successful_attempts = TestAttempt.objects.filter(
            status=TestAttempt.PASSED,
            end_time__range=(start_date, end_date)  # Учитываем только те, которые завершились в заданном периоде
        )

        # Группируем успешные попытки прохождения теста по тесту и вычисляем среднюю и максимальную продолжительность
        test_statistics = successful_attempts.values('test').annotate(
            avg_duration=Avg(
                ExpressionWrapper(
                    F('end_time') - F('start_time'),
                    output_field=DurationField()
                )
            ),
            max_duration=Max(
                ExpressionWrapper(
                    F('end_time') - F('start_time'),
                    output_field=DurationField()
                )
            )
        )

        # Возвращаем результаты
        return Response({
            'test_statistics': list(test_statistics)
        })
@api_view(['GET'])
def reattempt_delay(request, employee_id, test_id):
    try:
        # Находим сотрудника и тест по их идентификаторам
        employee = Employee.objects.get(id=employee_id)
        test = Test.objects.get(id=test_id)
    except (Employee.DoesNotExist, Test.DoesNotExist):
        return Response({"message": "Employee or Test not found"}, status=status.HTTP_404_NOT_FOUND)

    # Ищем последнюю попытку прохождения этого теста этим сотрудником
    last_attempt = TestAttempt.objects.filter(employee=employee, test=test).order_by('-end_time').first()

    if last_attempt:
        # Рассчитываем разницу во времени между последней попыткой и текущим временем
        time_since_last_attempt = timezone.now() - last_attempt.start_time

        # Рассчитываем оставшееся время до повторной попытки
        remaining_time = timedelta(days=test.retry_delay_days) - time_since_last_attempt

        # Получаем количество дней
        remaining_days = remaining_time.days

        if remaining_days >= 1:
            # Если осталось больше одного дня, выводим только количество дней
            return Response({"message": f"Reattempt available in {remaining_days} days"})
        elif remaining_time.total_seconds() <= 0:
            # Если время истекло
            return Response({"message": "Reattempt available now"})
        else:
            # Выводим количество оставшихся часов, либо сообщение о том, что осталось меньше часа
            remaining_hours, remaining_minutes = divmod(remaining_time.seconds, 3600)
            remaining_minutes //= 60

            if remaining_hours >= 1:
                return Response({"message": f"Reattempt available in {remaining_hours} hours"})
            else:
                return Response({"message": "Reattempt available in less than an hour"})
    else:
        # Если это первая попытка прохождения теста этим сотрудником
        return Response({"message": "Reattempt available now"})

@api_view(['GET'])
def review_test_attempts(request):
    if request.method == 'GET':
        # Получаем все попытки прохождения тестов на модерации
        test_attempts = TestAttempt.objects.filter(status=TestAttempt.MODERATION)

        # Сериализуем данные для вывода
        serializer = TestAttemptSerializer(test_attempts, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)


@csrf_exempt
@permission_classes([IsAdmin])
def reset_karma(request, employee_id=None):
    if request.method == 'POST':
        try:
            with transaction.atomic():
                if employee_id:
                    try:
                        employee = Employee.objects.get(pk=employee_id)
                    except ObjectDoesNotExist:
                        return JsonResponse({'status': 'error', 'message': 'Employee not found'}, status=404)

                    # Откатываем изменения кармы для конкретного сотрудника
                    karma_changes = KarmaHistory.objects.filter(employee=employee).aggregate(total_change=Sum('karma_change'))['total_change'] or 0
                    employee.karma -= karma_changes
                    employee.last_karma_update = None
                    employee.save()

                    # Удаляем историю кармы для конкретного сотрудника
                    KarmaHistory.objects.filter(employee=employee).delete()

                    return JsonResponse({'status': 'success', 'message': f'Karma history reset for employee {employee_id} successfully'})
                else:
                    # Откатываем изменения кармы для всех сотрудников
                    for employee in Employee.objects.all():
                        karma_changes = KarmaHistory.objects.filter(employee=employee).aggregate(total_change=Sum('karma_change'))['total_change'] or 0
                        employee.karma -= karma_changes
                        employee.last_karma_update = None
                        employee.save()

                    # Удаляем всю историю кармы
                    KarmaHistory.objects.all().delete()

                    return JsonResponse({'status': 'success', 'message': 'Karma history reset for all employees successfully'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)
@api_view(['DELETE'])
def delete_all_test_attempts(request):
    TestAttempt.objects.all().delete()
    return Response({"message": "All test attempts have been deleted."})

@api_view(['DELETE'])
def delete_test_attempt(request, attempt_id):
    try:
        test_attempt = TestAttempt.objects.get(id=attempt_id)
        test_attempt.delete()
        return Response({"message": f"Test attempt with id {attempt_id} has been deleted."})
    except TestAttempt.DoesNotExist:
        return Response({"message": "Test attempt not found."}, status=404)


@api_view(['GET'])
def get_test_duration(request, test_id):
    try:
        test = Test.objects.get(id=test_id)
    except Test.DoesNotExist:
        return Response({"message": "Test not found"}, status=status.HTTP_404_NOT_FOUND)

    # Получаем время на прохождение теста
    duration_seconds = test.duration_seconds

    return Response({"duration_seconds": duration_seconds}, status=status.HTTP_200_OK)
@api_view(['GET'])
def list_test_attempts(request):
    """
    Возвращает список всех попыток прохождения тестов.
    """
    test_attempts = TestAttempt.objects.all()
    serializer = TestAttemptSerializer(test_attempts, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def get_test_attempt(request, attempt_id):
    """
    Возвращает попытку прохождения теста по ее уникальному идентификатору (ID).
    """
    try:
        test_attempt = TestAttempt.objects.get(id=attempt_id)
        serializer = TestAttemptSerializer(test_attempt)
        return Response(serializer.data)
    except TestAttempt.DoesNotExist:
        return Response({"message": "TestAttempt not found"}, status=status.HTTP_404_NOT_FOUND)


class CreateQuestion(APIView):
    def post(self, request, format=None):
        # Извлекаем айдишник теста из данных запроса
        test_id = request.data.get('test')

        # Проверяем, что айдишник теста присутствует в запросе
        if not test_id:
            return Response({'error': 'Test ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Получаем объект теста по его айдишнику
        try:
            test = Test.objects.get(pk=test_id)
        except Test.DoesNotExist:
            return Response({'error': 'Test not found'}, status=status.HTTP_404_NOT_FOUND)

        # Создаем сериализатор для вопроса
        question_serializer = TestQuestionSerializer(data=request.data, context={'test': test})

        # Проверяем валидность данных для вопроса
        if question_serializer.is_valid():
            question_serializer.save()
        else:
            return Response(question_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Извлекаем данные ответов на вопрос
        answer_options_data = request.data.get('answer_options', [])

        # Создаем ответы на вопрос
        for answer_option_data in answer_options_data:
            answer_option_data['question'] = question_serializer.instance.pk  # Устанавливаем связь с вопросом
            answer_serializer = AnswerOptionSerializer(data=answer_option_data)
            if answer_serializer.is_valid():
                answer_serializer.save()
            else:
                return Response(answer_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response({'message': 'Question and answers created successfully'}, status=status.HTTP_201_CREATED)

class DeleteTest(generics.DestroyAPIView):
    queryset = Test.objects.all()
    serializer_class = TestSerializer
    lookup_field = 'id'  # Или какой у вас ключ в модели

class DeleteQuestion(generics.DestroyAPIView):
    queryset = TestQuestion.objects.all()
    serializer_class = TestQuestionSerializer
    lookup_field = 'id'  # Или какой у вас ключ в модели

class DeleteAnswer(generics.DestroyAPIView):
    queryset = AnswerOption.objects.all()
    serializer_class = AnswerOptionSerializer
    lookup_field = 'id'  # Или какой у вас ключ в модели


class UpdateTestAndContent(APIView):
    def put(self, request, test_id):
        try:
            test = Test.objects.get(id=test_id)
        except Test.DoesNotExist:
            return Response({"message": "Test not found"}, status=status.HTTP_404_NOT_FOUND)

        test_serializer = TestSerializer(test, data=request.data, partial=True)
        if not test_serializer.is_valid():
            return Response(test_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        blocks_data = request.data.get('blocks', [])

        created_questions = []
        created_theories = []
        created_answers = []

        try:
            with transaction.atomic():
                # Сначала сохраняем изменения в тесте
                test_serializer.save()

                # Удаляем старые вопросы, ответы и теории, связанные с тестом
                TestQuestion.objects.filter(test=test).delete()
                AnswerOption.objects.filter(question__test=test).delete()
                Theory.objects.filter(test=test).delete()

                # Создаем новые вопросы, теорию и сохраняем их в нужном порядке
                position = 1
                for block_data in blocks_data:
                    block_type = block_data.get('type')
                    content_data = block_data.get('content', {})
                    content_data['position'] = position  # Устанавливаем позицию
                    content_data['test'] = test.id

                    if block_type == 'question':
                        # Убираем id если он есть в данных
                        content_data.pop('id', None)
                        question_serializer = TestQuestionSerializer(data=content_data)
                        if question_serializer.is_valid():
                            question = question_serializer.save()
                            created_questions.append(question_serializer.data)
                            position += 1

                            # Сохраняем ответы для текущего вопроса
                            answers_data = block_data.get('content', {}).get('answer_options', [])
                            for answer_data in answers_data:
                                answer_data['question'] = question.id
                                # Убираем id если он есть в данных
                                answer_data.pop('id', None)
                                answer_serializer = AnswerOptionSerializer(data=answer_data)
                                if answer_serializer.is_valid():
                                    answer = answer_serializer.save()
                                    created_answers.append(answer_serializer.data)
                                else:

                                    return Response({"message": "Invalid answer data", "errors": answer_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
                        else:

                            return Response({"message": "Invalid question data", "errors": question_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
                    elif block_type == 'theory':
                        # Убираем id если он есть в данных
                        content_data.pop('id', None)
                        theory_serializer = TheorySerializer(data=content_data)
                        if theory_serializer.is_valid():
                            theory = theory_serializer.save()
                            created_theories.append(theory_serializer.data)
                            position += 1
                        else:

                            return Response({"message": "Invalid theory data", "errors": theory_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
                    else:
                        return Response({"message": "Invalid block type"}, status=status.HTTP_400_BAD_REQUEST)

                response_data = {
                    "message": "Test and content updated successfully",
                    "created_questions": created_questions,
                    "created_theories": created_theories,
                    "created_answers": created_answers
                }
                return Response(response_data, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)
class FullStatisticsAPIView(APIView):
    def get(self, request):
        # Initialize response dictionary
        response_data = {}

        # Statistics for test questions
        try:
            test_attempts = TestAttempt.objects.all()
            question_errors = Counter()
            question_correct = Counter()
            question_most_selected = {}

            for test_attempt in test_attempts:
                test_results = test_attempt.test_results

                # Ensure test_results is a dictionary
                if isinstance(test_results, str):
                    test_results = json.loads(test_results)

                if test_results:
                    answers_info = test_results.get("answers_info", [])

                    for answer_info in answers_info:
                        question_key = (answer_info["question_text"], test_attempt.test_id)

                        if not answer_info["is_correct"]:
                            question_errors[question_key] += 1
                        else:
                            question_correct[question_key] += 1

                        selected_option = answer_info.get("selected_option", "")
                        if selected_option:
                            if question_key not in question_most_selected:
                                question_most_selected[question_key] = Counter()
                            question_most_selected[question_key][selected_option] += 1

            most_common_errors = question_errors.most_common()
            most_common_correct = question_correct.most_common()
            most_common_selected = {k: v.most_common(1)[0] for k, v in question_most_selected.items()}

            response_data["most_common_errors"] = [
                {"question": q, "test_id": t, "count": c, "most_selected": most_common_selected.get((q, t))}
                for (q, t), c in most_common_errors
            ]
            response_data["most_common_correct"] = [
                {"question": q, "test_id": t, "count": c, "most_selected": most_common_selected.get((q, t))}
                for (q, t), c in most_common_correct
            ]
        except Exception as e:
            response_data["question_statistics_error"] = str(e)

        # Statistics for test duration
        try:
            test_stats = {}
            tests = Test.objects.all()

            for test in tests:
                test_attempts = TestAttempt.objects.filter(test=test, status=TestAttempt.PASSED)

                if test_attempts.exists():
                    durations = [
                        (attempt.end_time - attempt.start_time).total_seconds()
                        for attempt in test_attempts
                        if attempt.end_time and attempt.start_time
                    ]
                    if durations:
                        avg_duration = sum(durations) / len(durations)
                        max_duration = max(durations)
                    else:
                        avg_duration = None
                        max_duration = None

                    individual_durations = [
                        {"employee_id": attempt.employee_id, "duration": (attempt.end_time - attempt.start_time).total_seconds()}
                        for attempt in test_attempts
                        if attempt.end_time and attempt.start_time
                    ]

                    test_stats[test.id] = {
                        "average_duration": avg_duration,
                        "max_duration": max_duration,
                        "individual_durations": individual_durations
                    }
                else:
                    test_stats[test.id] = {
                        "average_duration": None,
                        "max_duration": None,
                        "individual_durations": []
                    }

            response_data["test_duration_statistics"] = test_stats
        except Exception as e:
            response_data["test_duration_statistics_error"] = str(e)

        # Statistics for employee achievements, currency, and experience
        try:
            employees = Employee.objects.all()
            employee_stats = []

            for employee in employees:
                employee_achievements = EmployeeAchievement.objects.filter(employee=employee)
                total_acoins = AcoinTransaction.objects.filter(employee=employee).aggregate(total=Sum('amount'))[
                    'total']
                employee_stats.append({
                    "employee_id": employee.id,
                    "total_acoins": total_acoins or 0,
                    "total_experience": employee.experience,
                    "total_achievements": employee_achievements.count()
                })

            response_data["employee_statistics"] = employee_stats
        except Exception as e:
            response_data["employee_statistics_error"] = str(e)

        # Statistics for test score percentage
        try:
            test_scores = {}
            for test in tests:
                test_attempts = TestAttempt.objects.filter(test=test, status=TestAttempt.PASSED)
                total_attempts = test_attempts.count()
                if total_attempts > 0:
                    total_correct_attempts = test_attempts.aggregate(Sum('score'))['score__sum']
                    if total_correct_attempts is not None:
                        percentage_correct = math.ceil((total_correct_attempts / total_attempts))
                    else:
                        percentage_correct = 0
                else:
                    percentage_correct = 0
                test_scores[test.id] = percentage_correct

            response_data["test_score_percentage"] = test_scores
        except Exception as e:
            response_data["test_score_percentage_error"] = str(e)

        # Statistics for most frequently selected answers
        try:
            most_selected_answers = {}
            for test_attempt in test_attempts:
                test_results = test_attempt.test_results
                if isinstance(test_results, str):
                    test_results = json.loads(test_results)
                if test_results:
                    answers_info = test_results.get("answers_info", [])
                    for answer_info in answers_info:
                        question_key = (answer_info["question_text"], test_attempt.test_id)
                        selected_option = answer_info.get("selected_option", "")
                        if selected_option:
                            if question_key not in most_selected_answers:
                                most_selected_answers[question_key] = Counter()
                            most_selected_answers[question_key][selected_option] += 1

            most_common_selected = {k: v.most_common(1)[0] for k, v in most_selected_answers.items()}
            response_data["most_common_selected_answers"] = [
                {"question": q, "test_id": t, "most_selected": most_common_selected.get((q, t))}
                for (q, t) in most_common_selected
            ]
        except Exception as e:
            response_data["most_common_selected_answers"] = [
                {"question": q, "test_id": t, "most_selected": most_common_selected.get((q, t))}
                for (q, t) in most_common_selected
            ]
        except Exception as e:
            response_data["most_selected_answers_error"] = str(e)

        return Response(response_data)


class UpdateTest(generics.UpdateAPIView):
    queryset = Test.objects.all()
    serializer_class = TestSerializer
    lookup_field = 'id'  # Или какой у вас ключ в модели

class UpdateQuestion(generics.UpdateAPIView):
    queryset = TestQuestion.objects.all()
    serializer_class = TestQuestionSerializer
    lookup_field = 'id'  # Или какой у вас ключ в модели

class UpdateAnswer(generics.UpdateAPIView):
    queryset = AnswerOption.objects.all()
    serializer_class = AnswerOptionSerializer
    lookup_field = 'id'  # Или какой у вас ключ в модели

class TheoryCreate(APIView):
    def post(self, request, format=None):
        serializer = TheorySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class TheoryList(APIView):
    def get(self, request, format=None):
        theories = Theory.objects.all()
        serializer = TheorySerializer(theories, many=True)
        return Response(serializer.data)
class TheoryDetail(RetrieveAPIView):
    queryset = Theory.objects.all()
    serializer_class = TheorySerializer
    lookup_field = 'id'
class TestQuestionDetail(APIView):
    def get(self, request, question_id, format=None):
        try:
            question = TestQuestion.objects.get(id=question_id)
            serializer = TestQuestionSerializer(question, context={'request': request})
            return Response(serializer.data)
        except TestQuestion.DoesNotExist:
            return Response({"error": "Question not found"}, status=status.HTTP_404_NOT_FOUND)

class CreateAnswer(APIView):
    def post(self, request, format=None):
        serializer = AnswerOptionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class AnswerOptionDetailView(RetrieveAPIView):
    queryset = AnswerOption.objects.all()
    serializer_class = AnswerOptionSerializer
    lookup_field = 'pk'

@api_view(['POST'])
def start_test_attempt(request, test_id, employee_id):
    if request.method == 'POST':
        try:
            employee = Employee.objects.get(id=employee_id)
            test = Test.objects.get(id=test_id)
        except (Employee.DoesNotExist, Test.DoesNotExist):
            return Response({"message": "Employee or Test not found"}, status=status.HTTP_404_NOT_FOUND)

        # Проверяем, что у сотрудника достаточно кармы для прохождения теста (если нужно)
        if employee.karma < test.required_karma:
            return Response({"message": "Insufficient karma to start the test"}, status=status.HTTP_400_BAD_REQUEST)

        # Создаем объект TestAttempt с начальным статусом IN_PROGRESS
        test_attempt = TestAttempt.objects.create(employee=employee, test=test, status=TestAttempt.IN_PROGRESS)

        # Возвращаем ответ с идентификатором попытки теста
        return Response({"message": "Test attempt started successfully.", "test_attempt_id": test_attempt.id},
                        status=status.HTTP_200_OK)