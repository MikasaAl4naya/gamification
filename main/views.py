import ast
import base64
import logging
import math
import re
import uuid
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from multiprocessing import Value

from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.db import transaction
from django.views.decorators.http import require_POST
from rest_framework.exceptions import NotFound
from .permissions import IsAdmin, IsModerator, IsUser, IsModeratorOrAdmin
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
import pytz
from django.contrib.auth import login, logout, get_user_model
from django.core.checks import messages
from django.core.serializers import serialize
from django.db.models import Max, FloatField, Avg, Count, Q, F, Sum, ExpressionWrapper, DurationField, OuterRef, \
    Subquery, Window, When, Case
from django.db.models.functions import Coalesce, RowNumber
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.models import User, Permission, Group
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.timezone import localtime
from rest_framework.fields import IntegerField
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import  BasePermission, IsAuthenticated, AllowAny
from rest_framework.utils import json
from json.decoder import JSONDecodeError
from .models import Achievement, Employee, EmployeeAchievement, TestQuestion, AnswerOption, Test, AcoinTransaction, \
    Acoin, TestAttempt, Theme, Classifications, FilePath, KarmaHistory
from rest_framework.generics import get_object_or_404
from .forms import AchievementForm, RequestForm, EmployeeRegistrationForm, EmployeeAuthenticationForm, QuestionForm, \
    AnswerOptionForm
from rest_framework.decorators import api_view, parser_classes, permission_classes, authentication_classes
from .serializers import TestQuestionSerializer, AnswerOptionSerializer, TestSerializer, AcoinTransactionSerializer, \
    AcoinSerializer, ThemeWithTestsSerializer, AchievementSerializer, RequestSerializer, ThemeSerializer, \
    ClassificationSerializer, TestAttemptModerationSerializer, TestAttemptSerializer, PermissionsSerializer, \
    GroupSerializer, PermissionSerializer, AdminEmployeeSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics, viewsets
from .serializers import LoginSerializer, EmployeeSerializer, EmployeeRegSerializer  # Импортируем сериализатор
from django.contrib.auth import authenticate
from .models import Theory
from .serializers import TheorySerializer
from .views_base import EmployeeAPIView


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


def save_base64_image(base64_image, filename_prefix):
    try:
        # Логирование перед началом декодирования
        print(f"Base64 image: {base64_image[:30]}...")

        # Декодируем изображение из base64
        format, imgstr = base64_image.split(';base64,')
        ext = format.split('/')[-1]
        if ext not in ['jpeg', 'jpg', 'png']:
            raise ValueError('Unsupported image format')

        img_data = base64.b64decode(imgstr)
        unique_filename = f"{filename_prefix}_{uuid.uuid4()}.{ext}"

        # Логирование перед возвратом
        print(f"Saving image as: {unique_filename}")

        return ContentFile(img_data, name=unique_filename)
    except Exception as e:
        raise ValueError(f'Error saving image: {str(e)}')


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
@permission_classes([IsAdmin])
def deactivate_user(request, user_id):
    try:
        employee = Employee.objects.get(id=user_id)
        employee.deactivate()
        return Response({"message": "User deactivated successfully"}, status=status.HTTP_200_OK)
    except Employee.DoesNotExist:
        return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    except ValidationError as e:
        return Response({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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


logger = logging.getLogger(__name__)
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
            logger.debug(f"User {request.user} has_perm {required_permission}: {has_perm}")
            return has_perm
        logger.debug("No required permission for this method")
        return False
class AchievementListView(generics.ListAPIView):
    queryset = Achievement.objects.all()
    serializer_class = AchievementSerializer
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
@permission_classes([IsAdmin])
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

@api_view(['GET'])
def get_user(request, user_id):
    try:
        # Получаем сотрудника по его ID
        employee = Employee.objects.get(id=user_id)

        # Получаем опыт и карму сотрудника
        experience = employee.experience
        karma = employee.karma

        # Получаем количество акоинов сотрудника
        acoin = Acoin.objects.get(employee=employee).amount

        # Создаем словарь с данными сотрудника
        user_data = {
            'id': employee.id,
            'username': employee.username,
            'email': employee.email,
            'position': employee.position,
            'level': employee.level,
            'experience': experience,
            'karma': karma,
            'acoin': acoin,
            'next_lvl_experience': employee.next_level_experience
        }

        # Возвращаем успешный ответ с данными сотрудника
        return Response(user_data)
    except Employee.DoesNotExist:
        # Если сотрудник не найден, возвращаем сообщение об ошибке
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

#@permission_classes([IsAdmin])
class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    permission_classes = [IsAdmin]


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
@permission_classes([IsAdmin])
class PermissionViewSet(viewsets.ModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
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


@permission_classes([IsAdmin])
def get_statistics():
    statistics = TestAttempt.objects.annotate(
        total_score=F('score'),
        max_score=F('test__max_score'),
        result=Case(
            When(is_passed=True, then=Value('Пройден')),
            When(is_failed=True, then=Value('Провален')),
            When(is_moderated=True, then=Value('На модерации')),
            default=Value('Не завершен'),
            output_field=IntegerField(),
        ),
        duration_seconds=ExpressionWrapper(
            F('end_time') - F('start_time'),
            output_field=IntegerField()
        ),
    ).values(
        'employee__full_name',
        'test__theme__name',
        'test__name',
        'total_score',
        'max_score',
        'result',
        'duration_seconds',
        'end_time__date',
    )

    return statistics

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


@permission_classes([IsAdmin])
@api_view(['POST'])
def change_password(request, user_id):
    try:
        employee = get_object_or_404(Employee, id=user_id)
        new_password = get_random_string(length=10)

        # Хешируем новый пароль
        hashed_password = make_password(new_password)

        # Устанавливаем хешированный пароль для пользователя и сохраняем его
        employee.password = hashed_password
        employee.save()

        # Отправка электронной почты с новым паролем
        subject = 'Ваш новый пароль'
        message = f'Здравствуйте, {employee.first_name}!\n\nВаш новый пароль: {new_password}\n'
        email = EmailMessage(subject, message, to=[employee.email])
        email.send()

        # Возвращаем сообщение об успешной смене пароля
        return Response({"message": "Password changed successfully and sent to email.","password": new_password}, status=status.HTTP_200_OK)


    except Exception as e:
        return Response({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)
@api_view(['POST'])
@permission_classes([IsAdmin])
def create_request(request):
    if request.method == 'POST':
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
            # Проверяем, является ли тип ачивки "Requests"
            if achievement_data['type'] == 'Requests':
                # Проверяем, что все необходимые поля заполнены
                if (achievement_data['required_count'] is None or
                        achievement_data['reward_experience'] is None or
                        achievement_data['reward_currency'] is None or
                        achievement_data['request_type'] is None):
                    return Response(
                        {"error": "All fields must be specified for achievements based on number of requests."},
                        status=status.HTTP_400_BAD_REQUEST)
            # Проверяем, является ли тип ачивки "Test"
            if achievement_data['type'] == 'Test':
                # Находим классификацию с названием "Test"
                try:
                    test_classification = Classifications.objects.get(name="Test")
                except Classifications.DoesNotExist:
                    return Response(
                        {"error": "No classification with name 'Test' found."},
                        status=status.HTTP_400_BAD_REQUEST)
                # Устанавливаем значение request_type в найденную классификацию
                serializer.validated_data['request_type'] = test_classification
                # Проверяем, что required_count равен 0
                serializer.validated_data['required_count'] = 0
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
    # Логирование входящего запроса
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
    if 'image' in request.data:
        base64_image = request.data.pop('image')
        if base64_image:
            try:
                filename = f"test_{request.data.get('name', 'unknown')}"
                request.data['image'] = save_base64_image(base64_image, filename)
            except ValueError as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    test_serializer = TestSerializer(data=request.data)

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
                base64_image = block_data['content'].pop('image')
                if base64_image:
                    try:
                        filename = f"question_{position}"
                        block_data['content']['image'] = save_base64_image(base64_image, filename)
                    except ValueError as e:
                        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

            serializer_class = TestQuestionSerializer
            created_list = created_questions
        elif block_data['type'] == 'theory':
            if 'image' in block_data['content']:
                base64_image = block_data['content'].pop('image')
                if base64_image:
                    try:
                        filename = f"theory_{position}"
                        block_data['content']['image'] = save_base64_image(base64_image, filename)
                    except ValueError as e:
                        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

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
@permission_classes([IsAuthenticated, IsModeratorOrAdmin])  # Добавили новую проверку прав доступа
def moderate_test_attempt(request, test_attempt_id):
    try:
        test_attempt = TestAttempt.objects.get(id=test_attempt_id)
    except TestAttempt.DoesNotExist:
        return Response({"message": "Test Attempt not found"}, status=status.HTTP_404_NOT_FOUND)

    # Получаем текущего пользователя
    moderator = request.user

    if 'moderated_questions' not in request.data:
        return Response({"message": "Moderated questions are required"}, status=status.HTTP_400_BAD_REQUEST)

    moderated_questions = request.data['moderated_questions']

    # Преобразуем строку test_results в словарь
    test_results = json.loads(test_attempt.test_results)

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

        # Обновляем поле is_correct в зависимости от модерационного балла
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

    response_data = {
        "score": test_attempt.score,
        "message": "Test moderated successfully",
        "status": test_attempt.status,
        "moderator": f"{moderator.first_name} {moderator.last_name}"
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
