import ast
import math
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import login, logout, get_user_model
from django.core.checks import messages
from django.core.serializers import serialize
from django.db.models import Max, FloatField, Avg, Count, Q, F, Sum, ExpressionWrapper, DurationField, OuterRef, \
    Subquery, Window
from django.db.models.functions import Coalesce, RowNumber
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.models import User, Permission
from django.utils import timezone
from django.utils.crypto import get_random_string
from rest_framework.generics import RetrieveAPIView
from rest_framework.utils import json

from .models import Achievement, Employee, EmployeeAchievement, TestQuestion, AnswerOption, Test, AcoinTransaction, \
    Acoin, TestAttempt, Theme, Classifications
from django.shortcuts import get_object_or_404, render, redirect
from .forms import AchievementForm, RequestForm, EmployeeRegistrationForm, EmployeeAuthenticationForm, QuestionForm, \
    AnswerOptionForm
from rest_framework.decorators import api_view
from .serializers import TestQuestionSerializer, AnswerOptionSerializer, TestSerializer, AcoinTransactionSerializer, \
    AcoinSerializer, ThemeWithTestsSerializer, AchievementSerializer, RequestSerializer, ThemeSerializer, \
    ClassificationSerializer, TestAttemptModerationSerializer, TestAttemptSerializer, PermissionsSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from .serializers import LoginSerializer, EmployeeSerializer, EmployeeRegSerializer  # Импортируем сериализатор
from django.contrib.auth import authenticate
from .models import Theory
from .serializers import TheorySerializer


class LoginAPIView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            # Получаем имя пользователя и пароль из данных запроса
            username = serializer.validated_data.get('username')
            password = serializer.validated_data.get('password')

            # Проверяем аутентификацию пользователя по имени пользователя и паролю
            user = authenticate(request, username=username, password=password)
            if user is not None:
                # Если пользователь успешно аутентифицирован, получаем его
                employee = Employee.objects.get(username=username)

                # Получаем опыт и карму сотрудника
                experience = employee.experience
                karma = employee.karma

                # Получаем количество акоинов сотрудника
                acoin = Acoin.objects.get(employee=employee).amount

                # Возвращаем успешный ответ с данными сотрудника
                return Response({'message': 'Login successful', 'employee_id': employee.id,
                                 'experience': experience, 'karma': karma, 'acoin': acoin},
                                status=status.HTTP_200_OK)
            else:
                # Если аутентификация не удалась, возвращаем сообщение об ошибке
                return Response({
                    'message': 'Invalid username or password',
                    'data': serializer.validated_data  # Возвращаем отправленные данные
                }, status=status.HTTP_401_UNAUTHORIZED)
        else:
            # Если данные запроса некорректны, возвращаем сообщение об ошибке
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



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
class PermissionsList(APIView):
    def get(self, request):
        permissions = Permission.objects.all()
        serializer = PermissionsSerializer(permissions, many=True)
        return Response(serializer.data)

@api_view(['GET'])
def latest_test_attempts(request):
    # Проверяем, принадлежит ли пользователь к группе модераторов или администраторов
    # is_moderator_or_admin = request.user.groups.filter(name__in=['Модераторы', 'Администраторы']).exists()
    #
    # if not is_moderator_or_admin:
    #     return Response({"error": "Доступ запрещен"}, status=status.HTTP_403_FORBIDDEN)
    # Используем оконную функцию для присвоения номера строки каждой попытке
    attempts_with_row_number = TestAttempt.objects.annotate(
        row_number=Window(
            expression=RowNumber(),
            partition_by=[F('employee_id'), F('test_id')],
            order_by=F('end_time').desc()
        )
    ).filter(row_number=1).select_related('employee', 'test', 'test__theme')

    # Формируем словарь с результатами, сгруппированными по сотруднику и теме теста
    grouped_result = defaultdict(lambda: defaultdict(list))
    for attempt in attempts_with_row_number:
        employee_name = attempt.employee.first_name + " " + attempt.employee.last_name  # предположим, что у модели Employee есть поле name
        theme_name = attempt.test.theme.name  # предположим, что у модели Test есть ForeignKey на Theme с полем name
        test_attempt = attempt.id
        test_info = {
            'test_attempt': test_attempt,
            'test_name': attempt.test.name,  # предположим, что у модели Test есть поле name
            'score': attempt.score,
            'max_score': attempt.test.max_score,  # предположим, что у модели Test есть поле max_score
            'status': attempt.status,
            'end_time': attempt.end_time.strftime("%Y-%m-%dT%H:%M") if attempt.end_time else None  # Добавляем дату окончания теста
        }

        grouped_result[employee_name][theme_name].append(test_info)

    # Формируем окончательный результат и сортируем по имени сотрудника
    sorted_result = [
        {
            'employee': employee,
            'themes': [
                {
                    'theme_name': theme,
                    'tests': tests
                }
                for theme, tests in sorted(themes.items())
            ]
        }
        for employee, themes in sorted(grouped_result.items())
    ]

    return Response(sorted_result, status=status.HTTP_200_OK)

class MostIncorrectQuestionsAPIView(APIView):
    def get(self, request):
        # Получаем список вопросов, по которым сотрудники чаще всего ошибаются
        most_incorrect_questions = TestQuestion.objects.annotate(
            incorrect_count=Count('testattemptquestionexplanation', filter=~Q(testattemptquestionexplanation__is_correct=True))
        ).order_by('-incorrect_count')[:10]

        # Формируем список вопросов и количества ошибок для каждого вопроса
        result = [{'question_text': question.text, 'incorrect_count': question.incorrect_count} for question in most_incorrect_questions]

        return Response(result)



from django.db import transaction, IntegrityError




class EmployeeDetails(APIView):
    def get(self, request, username):
        try:
            employee = Employee.objects.get(username=username)
            serializer = EmployeeSerializer(employee)
            return Response(serializer.data)
        except Employee.DoesNotExist:
            return Response({"message": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)







class RegisterAPIView(APIView):
    @transaction.atomic
    def post(self, request):
        serializer = EmployeeRegSerializer(data=request.data)
        if serializer.is_valid():
            # Создание сотрудника
            employee = serializer.save()

            # Генерация пароля
            password = get_random_string(length=10)

            # Сохранение сгенерированного пароля в сотруднике
            employee.set_password(password)
            employee.save()

            # Сохранение сгенерированного пароля в сессии
            request.session['generated_password'] = password

            # Возвращение успешного ответа
            return Response({
                'message': 'Registration successful',
                'generated_password': password
            }, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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


@api_view(['DELETE'])
def delete_all_tests(request):
    if request.method == 'DELETE':
        # Получаем все объекты модели Test
        tests = Test.objects.all()

        # Удаляем все тесты
        tests.delete()

        return Response({"message": "All tests have been deleted"}, status=status.HTTP_204_NO_CONTENT)
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


class UpdateTestAndContent(APIView):
    def put(self, request, test_id):
        try:
            test = Test.objects.get(id=test_id)
        except Test.DoesNotExist:
            return Response({"message": "Test not found"}, status=status.HTTP_404_NOT_FOUND)

        test_serializer = TestSerializer(test, data=request.data, partial=True)
        if test_serializer.is_valid():
            test_serializer.save()

            # Удаление старых вопросов, ответов и теории
            test.questions.all().delete()
            test.theory.delete()

            # Создание новых вопросов
            if 'questions' in request.data:
                questions_data = request.data['questions']
                for question_data in questions_data:
                    question_serializer = TestQuestionSerializer(data=question_data)
                    if question_serializer.is_valid():
                        question_serializer.save(test=test)

            # Создание новых ответов
            if 'answers' in request.data:
                answers_data = request.data['answers']
                for answer_data in answers_data:
                    answer_serializer = AnswerOptionSerializer(data=answer_data)
                    if answer_serializer.is_valid():
                        answer_serializer.save()

            # Создание новой теории
            if 'theory' in request.data:
                theory_data = request.data['theory']
                theory_serializer = TheorySerializer(data=theory_data)
                if theory_serializer.is_valid():
                    theory_serializer.save(test=test)

            return Response({"message": "Test and content updated successfully"}, status=status.HTTP_200_OK)
        else:
            return Response(test_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
    except (TypeError, json.JSONDecodeError):
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

        # Добавляем проверку для частично правильных текстовых ответов
        if answer_info.get("type") == "text" and answer_info.get("is_partially_true", False):
            answer_info["partial_correct_message"] = "Ответ частично верный"

    response_data = {
        "score": test_attempt.score,
        "max_score": test_results.get("Максимальное количество баллов"),
        "status": test_attempt.status,
        "answers_info": answers_info,
        "test_creation_date": test.created_at.strftime("%Y-%m-%d %H:%M:%S") if test.created_at else None,
        "test_end_date": test_attempt.end_time.strftime("%Y-%m-%d %H:%M:%S") if test_attempt.end_time else None,
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

    return Response(response_data, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_test_by_id(request, test_id):
    # Получаем тест по его ID или возвращаем ошибку 404, если тест не найден
    test = get_object_or_404(Test, id=test_id)

    # Сериализуем данные теста
    test_serializer = TestSerializer(test)

    # Получаем все вопросы и теорию для данного теста, отсортированные по позиции
    questions = TestQuestion.objects.filter(test=test).order_by('position')
    theories = Theory.objects.filter(test=test).order_by('position')

    # Создаем список для хранения блоков теста
    blocks = []

    # Добавляем данные о вопросах в список блоков
    for question in questions:
        block_data = {
            'type': 'question',
            'content': TestQuestionSerializer(question).data
        }
        blocks.append(block_data)

    # Добавляем данные о теории в список блоков
    for theory in theories:
        block_data = {
            'type': 'theory',
            'content': TheorySerializer(theory).data
        }
        blocks.append(block_data)

    # Сортируем блоки по позиции, если она есть
    sorted_blocks = sorted(blocks, key=lambda x: x['content'].get('position', 0))

    # Добавляем позицию вопроса к соответствующим блокам
    for block in sorted_blocks:
        if block['type'] == 'question':
            block['content']['position'] = TestQuestion.objects.get(id=block['content']['id']).position
        elif block['type'] == 'theory':
            block['content']['position'] = Theory.objects.get(id=block['content']['id']).position

    # Возвращаем данные о тесте и его блоках
    response_data = {
        'test': test_serializer.data,
        'blocks': sorted_blocks
    }
    return Response(response_data)


@api_view(['GET'])
def get_themes_with_tests(request, employee_id):
    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return Response({"message": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)

    # Получаем все темы
    themes = Theme.objects.all().order_by('name')

    # Создаем список для хранения тем с их связанными тестами
    themes_with_tests = []

    # Проходимся по всем темам
    for theme in themes:
        # Получаем все тесты, связанные с текущей темой
        tests = Test.objects.filter(theme=theme)

        # Создаем список для хранения информации о тестах
        tests_info = []

        # Проходимся по всем тестам и собираем информацию о каждом из них
        for test in tests:
            created_at = test.created_at.strftime("%Y-%m-%dT%H:%M")

            # Проверяем наличие попыток прохождения теста
            test_attempt = TestAttempt.objects.filter(employee=employee, test=test).last()
            if test_attempt:
                if test_attempt.test_results:
                    try:
                        # Десериализуем строку JSON в объект Python
                        test_results = json.loads(test_attempt.test_results)
                        total_score = test_results.get("Набранное количество баллов", 0)
                        max_score = test.max_score
                        answers_info = test_results.get("answers_info", [])
                        test_status = {
                            "status": test_attempt.status,
                            "total_score": total_score,
                            "max_score": max_score
                        }
                    except (json.JSONDecodeError, TypeError, KeyError):
                        test_status = None
                else:
                    # Если попытка есть, но результатов еще нет, то статус "Не начато"
                    test_status = {"status": "Не начато", "total_score": 0, "max_score": 0}
            else:
                # Если попытки прохождения теста нет, то статус "Не начато"
                test_status = {"status": "Не начато", "total_score": 0, "max_score": 0}

            # Проверка достаточно ли у сотрудника опыта и кармы для прохождения теста
            has_sufficient_karma = employee.karma >= test.required_karma
            has_sufficient_experience = employee.experience >= test.min_experience

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
                'has_sufficient_experience': has_sufficient_experience
            }

            tests_info.append(test_info)

        # Добавляем информацию о текущей теме и ее тестах в список
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
@api_view(['POST'])
def create_request(request):
    if request.method == 'POST':
        serializer = RequestSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class ThemeDeleteAPIView(APIView):
    def delete(self, request, theme_id):
        try:
            theme = Theme.objects.get(id=theme_id)
        except Theme.DoesNotExist:
            return Response({"message": "Theme not found"}, status=status.HTTP_404_NOT_FOUND)

        theme.delete()
        return Response({"message": "Theme deleted successfully"}, status=status.HTTP_204_NO_CONTENT)

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


@api_view(['POST'])
def create_classification(request):
    if request.method == 'POST':
        # Извлекаем название классификации из запроса
        name = request.data.get('name')

        # Проверяем, не пустое ли название
        if name:
            # Пытаемся найти классификацию по названию
            try:
                existing_classification = Classifications.objects.get(name=name)
                # Если классификация с таким названием уже существует, возвращаем ошибку
                return Response({'error': 'Classification with this name already exists'},
                                status=status.HTTP_400_BAD_REQUEST)
            except Classifications.DoesNotExist:
                # Если классификация с таким названием не найдена, создаем новую
                classification_data = {'name': name}
                serializer = ClassificationSerializer(data=classification_data)
                if serializer.is_valid():
                    serializer.save()
                    return Response(serializer.data, status=status.HTTP_201_CREATED)
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Если название не было указано в запросе, возвращаем ошибку
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
def create_test(request):
    # Получаем данные о блоках из запроса
    blocks_data = request.data.get('blocks', [])

    # Проверяем, есть ли вопросы в блоках
    if not any(block['type'] == 'question' for block in blocks_data):
        return Response({'error': 'Test must contain at least one question'}, status=status.HTTP_400_BAD_REQUEST)

    # Создаем сериализатор теста
    test_serializer = TestSerializer(data=request.data)

    # Проверяем валидность данных теста
    if not test_serializer.is_valid():
        return Response(test_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Сохраняем тест
    test = test_serializer.save()

    # Списки для хранения созданных вопросов, теории и ответов
    created_questions = []
    created_theories = []
    created_answers = []

    # Устанавливаем начальную позицию для блоков
    position = 1

    for block_data in blocks_data:
        # Добавляем айдишник теста в данные о блоке
        block_data['content']['test'] = test.id

        # Определяем тип блока: вопрос или теория
        if block_data['type'] == 'question':
            serializer_class = TestQuestionSerializer
            created_list = created_questions
        elif block_data['type'] == 'theory':
            serializer_class = TheorySerializer
            created_list = created_theories
        else:
            return Response({'error': 'Invalid block type'}, status=status.HTTP_400_BAD_REQUEST)

        # Создаем сериализатор для блока
        block_serializer = serializer_class(data=block_data['content'])
        if not block_serializer.is_valid():
            return Response(block_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Сохраняем блок
        block = block_serializer.save(position=position)
        created_list.append(block_serializer.data)

        # Если это вопрос, сохраняем ответы
        if block_data['type'] == 'question':
            # Получаем данные об ответах из блока вопроса
            answers_data = block_data['content'].get('answer_options', [])

            # Сохраняем ответы для текущего вопроса
            for answer_data in answers_data:
                # Добавляем айдишник вопроса в данные об ответе
                answer_data['question'] = block.id

                # Создаем сериализатор для ответа
                answer_serializer = AnswerOptionSerializer(data=answer_data)
                if not answer_serializer.is_valid():
                    return Response(answer_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

                # Сохраняем ответ
                answer = answer_serializer.save()
                created_answers.append(answer_serializer.data)

            # Выводим количество правильных ответов для текущего вопроса
            correct_answers_count = len([answer for answer in answers_data if answer.get('is_correct')])
            print(correct_answers_count)

        # Увеличиваем позицию для следующего блока
        position += 1

    # Возвращаем успешный ответ с информацией о созданных блоках
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
    # Получаем все попытки прохождения тестов на модерации
    test_attempts_moderation = TestAttempt.objects.filter(status=TestAttempt.MODERATION)

    # Сортируем по темам тестов
    sorted_attempts = sorted(test_attempts_moderation, key=lambda x: x.test.theme.name)

    # Группируем по темам тестов
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
def moderate_test_attempt(request, test_attempt_id):
    if request.method == 'POST':
        try:
            test_attempt = TestAttempt.objects.get(id=test_attempt_id)
        except TestAttempt.DoesNotExist:
            return Response({"message": "Test Attempt not found"}, status=status.HTTP_404_NOT_FOUND)

        # Проверяем, что запрос содержит необходимые данные
        if 'moderated_questions' not in request.data:
            return Response({"message": "Moderated questions are required"}, status=status.HTTP_400_BAD_REQUEST)

        moderated_questions = request.data['moderated_questions']

        # Преобразуем строку test_results в словарь
        test_results = json.loads(test_attempt.test_results)

        # Получаем информацию о ответах на вопросы
        answers_info = test_results.get('answers_info', [])

        # Проверяем, находится ли тест на модерации
        if test_attempt.status != TestAttempt.MODERATION:
            return Response({"message": "Test attempt is not on moderation"}, status=status.HTTP_400_BAD_REQUEST)

        for moderated_question in moderated_questions:
            question_number = moderated_question.get('question_number')
            moderation_score = moderated_question.get('moderation_score')
            moderation_comment = moderated_question.get('moderation_comment', '')

            # Проверяем, что номер вопроса корректный
            if question_number < 1 or question_number > len(answers_info):
                return Response({"message": "Invalid question number"}, status=status.HTTP_400_BAD_REQUEST)

            # Находим вопрос, который нужно модерировать
            question_to_moderate = answers_info[question_number - 1]

            # Проверяем, что вопрос имеет тип "text"
            if 'type' not in question_to_moderate or question_to_moderate['type'] != 'text':
                return Response({"message": "You can only moderate questions with type 'text'"}, status=status.HTTP_400_BAD_REQUEST)

            # Получаем максимальное количество баллов, которое можно установить за ответ на вопрос
            max_question_score = question_to_moderate.get('max_question_score', 0)

            # Проверяем, что установленное количество баллов не превышает максимальное
            if moderation_score > max_question_score:
                return Response({"message": f"Moderation score exceeds the maximum allowed score ({max_question_score})"}, status=status.HTTP_400_BAD_REQUEST)

            # Обновляем баллы за вопрос и комментарий модератора
            question_to_moderate['question_score'] = moderation_score
            question_to_moderate['moderation_comment'] = moderation_comment

            # Определяем статус ответа
            if moderation_score == max_question_score:
                question_to_moderate['is_correct'] = True
                question_to_moderate['is_partially_true'] = False  # Убедимся, что нет флага частично верного
            else:
                question_to_moderate['is_correct'] = False
                question_to_moderate['is_partially_true'] = True

        # Пересчитываем общее количество баллов
        total_score = sum(question.get('question_score', 0) for question in answers_info)
        total_score = round(total_score, 1)  # Округляем до десятых

        # Обновляем общее количество баллов в объекте TestAttempt
        test_attempt.score = total_score

        # Проверяем, пройден ли тест
        if total_score >= test_attempt.test.passing_score:
            test_attempt.status = TestAttempt.PASSED
        else:
            test_attempt.status = TestAttempt.FAILED

        # Сохраняем изменения
        test_attempt.end_time = timezone.now()  # Устанавливаем время окончания модерации
        test_attempt.save()

        response_data = {
            "score" : test_attempt.score,
            "message": "Test moderated successfully",
            "status": test_attempt.status
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


@api_view(['POST'])
def start_test(request, employee_id, test_id):
    if request.method == 'POST':
        try:
            employee = Employee.objects.get(id=employee_id)
            test = Test.objects.get(id=test_id)
        except (Employee.DoesNotExist, Test.DoesNotExist):
            return Response({"message": "Employee or Test not found"}, status=status.HTTP_404_NOT_FOUND)

        # Проверка на достаточно опыта и кармы у сотрудника (раскомментируйте, если требуется)
        # if employee.experience < test.experience_points:
        #     return Response({"message": "Not enough experience to start this test"},
        #                     status=status.HTTP_400_BAD_REQUEST)
        #
        # if employee.karma < test.required_karma:
        #     return Response({"message": "Not enough karma to start this test"},
        #                     status=status.HTTP_400_BAD_REQUEST)

        # Проверка на наличие обязательного предыдущего теста
        required_test = test.required_test
        if required_test:
            if not TestAttempt.objects.filter(employee=employee, test=required_test, status=TestAttempt.PASSED).exists():
                return Response({"message": f"You must pass test {required_test.id} before starting this test"},
                                status=status.HTTP_400_BAD_REQUEST)

        # Проверка на наличие старых попыток в статусе "В процессе" или "Не начат"
        old_attempts = TestAttempt.objects.filter(
            employee=employee, test=test, status__in=[TestAttempt.IN_PROGRESS, TestAttempt.NOT_STARTED]
        )

        if old_attempts.exists():
            old_attempts.delete()

        # Создаем новую попытку прохождения теста с тем же ID, если старая попытка была удалена
        test_attempt = TestAttempt.objects.create(
            employee=employee,
            test=test,
            status=TestAttempt.IN_PROGRESS  # Устанавливаем статус "в процессе"
        )

        # Возвращаем идентификатор только что созданного TestAttempt
        return Response({"test_attempt_id": test_attempt.id}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def complete_test(request, employee_id, test_id):
    if request.method == 'POST':
        try:
            employee = Employee.objects.get(id=employee_id)
            test = Test.objects.get(id=test_id)
        except (Employee.DoesNotExist, Test.DoesNotExist):
            return Response({"message": "Employee or Test not found"}, status=status.HTTP_404_NOT_FOUND)

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

                # Инициализируем переменную is_correct
                is_correct = False

                # Вычисляем количество баллов за текущий вопрос
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
                    # Для вопросов с типом "text" сохраняем текстовый ответ
                    submitted_text_answer = submitted_answer
                    question_score = Decimal('0.0')
                elif question.question_type == 'multiple':
                    if isinstance(submitted_answer, int):
                        submitted_answer = [submitted_answer]  # Если только один вариант был выбран, преобразуем его в список
                    submitted_answer_numbers = [int(answer) for answer in submitted_answer]
                    correct_option_numbers = [index + 1 for index, option in enumerate(answer_options) if option['is_correct']]

                    # Считаем количество выбранных правильных и неправильных ответов
                    selected_correct_answers = sum(1 for answer in submitted_answer_numbers if answer in correct_option_numbers)
                    selected_incorrect_answers = sum(1 for answer in submitted_answer_numbers if answer not in correct_option_numbers)

                    # Рассчитываем баллы за каждый правильный и неправильный ответ
                    question_score_per_correct_answer = Decimal(str(question.points)) / Decimal(len(correct_option_numbers))
                    question_score_per_incorrect_answer = Decimal(str(question.points)) / Decimal(len(correct_option_numbers))

                    # Вычисляем итоговый балл за вопрос
                    question_score = (selected_correct_answers * question_score_per_correct_answer) - (selected_incorrect_answers * question_score_per_incorrect_answer)

                    # Не позволяем общему баллу за вопрос быть отрицательным
                    if question_score < 0:
                        question_score = Decimal('0.0')

                    if selected_correct_answers == len(correct_option_numbers) and selected_incorrect_answers == 0:
                        is_correct = True

                    total_score += question_score

                # Округляем балл до десятых
                question_score = question_score.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)

                # Обновляем данные в answers_info
                answer_info = {
                    "question_text": question_text,
                    "type": question.question_type,
                    "is_correct": is_correct,
                    "question_score": float(question_score),
                    "answer_options": [],
                    "explanation": question.explanation
                }
                if question.question_type == 'text':
                    # Добавляем текстовый ответ в информацию о вопросе
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

        # Округляем общий балл до десятых
        total_score = total_score.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)

        # Обновляем данные в test_attempt
        test_attempt.score = float(total_score)
        test_attempt.end_time = timezone.now()
        test_attempt.save()

        # Сохраняем ответы сотрудника и вопросы в test_attempt
        test_attempt.test_results = json.dumps({
            "Набранное количество баллов": float(total_score),
            "Максимальное количество баллов": float(max_score),
            "answers_info": answers_info
        }, ensure_ascii=False)
        test_attempt.save()

        # Проверяем наличие вопросов типа 'text'
        has_text_questions = TestQuestion.objects.filter(test=test, question_type='text').exists()

        # Проверяем, пройден ли тест
        if total_score >= Decimal(str(test.passing_score)):
            test_attempt.status = TestAttempt.PASSED
        elif has_text_questions:
            test_attempt.status = TestAttempt.MODERATION
        else:
            test_attempt.status = TestAttempt.FAILED

        # Сохраняем изменения в объекте test_attempt
        test_attempt.save()
        response_data = {
            "status": test_attempt.status,
            "test_attempt_id": test_attempt.id
        }
        return Response(response_data, status=status.HTTP_200_OK)


class QuestionErrorAPIView(APIView):
    def get(self, request, test_id):
        # Получаем все попытки прохождения теста
        test_attempts = TestAttempt.objects.filter(test_id=test_id)

        # Список для хранения количества неправильных ответов на каждый вопрос
        question_errors = Counter()

        # Проходим по каждой попытке
        for test_attempt in test_attempts:
            # Проверяем, что test_results не является None
            if test_attempt.test_results:
                test_results = json.loads(test_attempt.test_results)
                answers_info = test_results.get("answers_info", [])

                # Для каждого вопроса проверяем, был ли ответ неправильным
                for answer_info in answers_info:
                    if not answer_info["is_correct"]:
                        question_errors[answer_info["question_text"]] += 1

        # Находим список вопросов, на которые чаще всего ошибаются
        most_common_errors = question_errors.most_common()

        # Возвращаем список вопросов
        return Response({"most_common_errors": most_common_errors})

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
class QuestionStatisticsAPIView(APIView):
    def get(self, request):
        # Создаем словари для хранения информации о частоте ошибок и правильных ответов
        error_counter = Counter()
        correct_counter = Counter()

        # Обходим все попытки прохождения тестов
        for attempt in TestAttempt.objects.all():
            # Получаем результаты теста для текущей попытки
            test_results = attempt.test_results
            if isinstance(test_results, str):
                # Если test_results - строка, пытаемся преобразовать ее в словарь
                try:
                    results_dict = json.loads(test_results)
                    for answer_info in results_dict.get("answers_info", []):
                        # Проверяем, является ли ответ неправильным или правильным
                        if not answer_info["is_correct"]:
                            error_counter[(answer_info["question_text"], attempt.test_id)] += 1
                        else:
                            correct_counter[(answer_info["question_text"], attempt.test_id)] += 1
                except ValueError:
                    # Если не удалось преобразовать строку в JSON, пропускаем эту попытку
                    pass

        # Получаем список вопросов, по которым чаще всего ошибаются
        most_common_errors = error_counter.most_common()

        # Получаем список вопросов, на которые чаще всего отвечают верно
        most_common_correct = correct_counter.most_common()

        return Response({
            "most_common_errors": most_common_errors,
            "most_common_correct": most_common_correct
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
class QuestionSuccessAPIView(APIView):
    def get(self, request, test_id):
        # Получаем все попытки прохождения теста
        test_attempts = TestAttempt.objects.filter(test_id=test_id)

        # Список для хранения количества правильных ответов на каждый вопрос
        question_successes = Counter()

        # Проходим по каждой попытке
        for test_attempt in test_attempts:
            test_results = json.loads(test_attempt.test_results)
            answers_info = test_results.get("answers_info", [])

            # Для каждого вопроса проверяем, был ли ответ правильным
            for answer_info in answers_info:
                if answer_info["is_correct"]:
                    question_successes[answer_info["question_text"]] += 1

        # Находим список вопросов, на которые чаще всего отвечают правильно
        most_common_successes = question_successes.most_common()

        # Возвращаем список вопросов
        return Response({"most_common_successes": most_common_successes})
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
#основное обновление тестов
class UpdateTestAndContent(APIView):
    def put(self, request, test_id):
        try:
            test = Test.objects.get(id=test_id)
        except Test.DoesNotExist:
            return Response({"message": "Test not found"}, status=status.HTTP_404_NOT_FOUND)

        test_serializer = TestSerializer(test, data=request.data, partial=True)
        if test_serializer.is_valid():
            test_serializer.save()

            # Удаляем все старые вопросы и теории, связанные с тестом
            TestQuestion.objects.filter(test=test).delete()
            Theory.objects.filter(test=test).delete()

            # Обновление блоков
            if 'blocks' in request.data:
                blocks_data = request.data['blocks']
                position = 1  # Инициализация счетчика позиции
                for block_data in blocks_data:
                    if block_data['type'] == 'question':
                        question_data = block_data['content']
                        question_data['test'] = test.id  # Устанавливаем связь с тестом
                        question_serializer = TestQuestionSerializer(data=question_data)
                        if question_serializer.is_valid():
                            question_instance = question_serializer.save(position=position)  # Устанавливаем позицию вопроса
                            position += 1  # Увеличиваем счетчик позиции

                            # Сохраняем ответы для текущего вопроса
                            answers_data = question_data.get('answer_options', [])
                            for answer_data in answers_data:
                                answer_data['question'] = question_instance.id
                                answer_serializer = AnswerOptionSerializer(data=answer_data)
                                if answer_serializer.is_valid():
                                    answer_serializer.save()

                    elif block_data['type'] == 'theory':
                        theory_data = block_data['content']
                        theory_data['test'] = test.id  # Устанавливаем связь с тестом
                        theory_serializer = TheorySerializer(data=theory_data)
                        if theory_serializer.is_valid():
                            theory_serializer.save(position=position)  # Устанавливаем позицию теории
                            position += 1  # Увеличиваем счетчик позиции

            return Response({"message": "Test and content updated successfully"}, status=status.HTTP_200_OK)
        else:
            return Response(test_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
                acoin_transactions = AcoinTransaction.objects.filter(employee=employee)
                total_acoins = acoin_transactions.aggregate(total=Sum('amount'))['total']

                employee_stats.append({
                    "employee_id": employee.id,
                    "total_acoins": total_acoins or 0,
                    "total_experience": employee.experience,
                    "total_achievements": employee.achievement_set.count()  # Make sure you have related_name='achievement_set' in your Achievement model
                })

            response_data["employee_statistics"] = employee_stats
        except Exception as e:
            response_data["employee_statistics_error"] = str(e)

        return Response(response_data)

from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Avg, Max, Sum
import json
from collections import Counter
from .models import Test, TestAttempt, Employee, AcoinTransaction

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
