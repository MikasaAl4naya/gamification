import ast
from datetime import timedelta

from django.contrib.auth import login, logout
from django.core.checks import messages
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.models import User
from django.utils import timezone
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
    ClassificationSerializer, TestAttemptSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from .serializers import LoginSerializer, EmployeeSerializer, EmployeeRegSerializer  # Импортируем сериализатор
from django.contrib.auth import authenticate
from .models import Theory
from .serializers import TheorySerializer


def test_constructor(request):
    return render(request, 'test_constructor.html')

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
                # Если пользователь успешно аутентифицирован, возвращаем успешный ответ с данными пользователя
                employee = Employee.objects.get(username=username)
                employee_serializer = EmployeeSerializer(employee)
                return Response({'message': 'Login successful', 'employee': employee_serializer.data},
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




def index(request):
    return HttpResponse("Hello, world. You're at the")

def achievement_list(request):
    achievements = Achievement.objects.all()
    return render(request, 'achievement_list.html', {'achievements': achievements})

def create_achievement(request):
    if request.method == 'POST':
        form = AchievementForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('achievement_list')  # Перенаправляем пользователя на список ачивок после создания
    else:
        form = AchievementForm()
    return render(request, 'create_achievement.html', {'form': form})

def create_request(request):
    if request.method == 'POST':
        form = RequestForm(request.POST)
        if form.is_valid():
            form.save()
            # return redirect('success')  # Перенаправляем на страницу "успешного создания"
    else:
        form = RequestForm()
    return render(request, 'create_request.html', {'form': form})


from django.db import transaction

@transaction.atomic
def register(request):
    if request.method == 'POST':
        form = EmployeeRegistrationForm(request.POST)
        if form.is_valid():
            # Генерация случайного пароля
            password = User.objects.make_random_password()

            # Создание пользователя и сотрудника внутри одной транзакции
            user = User.objects.create_user(username=form.cleaned_data['email'].split('@')[0], password=password)
            employee = form.save(commit=False)
            employee.user = user
            employee.username = user.username

            # Сохранение сотрудника
            employee.save()

            # Сохранение сгенерированного пароля в сессии
            request.session['generated_password'] = password

            # Отображение страницы успешной регистрации
            return redirect('registration_success')

    else:
        form = EmployeeRegistrationForm()
    return render(request, 'register_employee.html', {'form': form})

def registration_success(request):
    # Получение сгенерированного пароля из сессии
    generated_password = request.session.pop('generated_password', None)

    if generated_password:
        # Отображение страницы успешной регистрации с сгенерированным паролем
        return render(request, 'registration_success.html', {'generated_password': generated_password})
    else:
        # Если сгенерированный пароль отсутствует, вернуть сообщение об ошибке
        messages.error(request, "Generated password not found.")
        return redirect('register_employee')

class EmployeeDetails(APIView):
    def get(self, request, username):
        try:
            employee = Employee.objects.get(username=username)
            serializer = EmployeeSerializer(employee)
            return Response(serializer.data)
        except Employee.DoesNotExist:
            return Response({"message": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)


def user_login(request):
    if request.method == 'POST':
        form = EmployeeAuthenticationForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                # Сохранение идентификатора пользователя в сессии
                request.session['user_id'] = user.id
                return redirect('user_profile')
            else:
                print('Неверные учетные данные')
        else:
            print('Форма не прошла валидацию')
    else:
        form = EmployeeAuthenticationForm()
    return render(request, 'login.html', {'form': form})

def some_other_view(request):
    # Получение идентификатора пользователя из сессии
    user_id = request.session.get('user_id')
    if user_id:
        # Получение объекта пользователя из базы данных
        user = User.objects.get(pk=user_id)
        # Использование пользователя для выполнения нужных действий
        # Например, передача его в шаблон для отображения информации о пользователе
        return render(request, 'some_template.html', {'user': user})
    else:
        # Если пользователь не аутентифицирован, выполните необходимые действия
        return render(request, 'not_authenticated.html')

def logout_view(request):
    # Удаление идентификатора пользователя из сессии
    if 'user_id' in request.session:
        del request.session['user_id']
    # Выход пользователя из системы
    logout(request)
    # Перенаправление на нужную страницу
    return redirect('user_profile')


def user_profile(request):
    if request.user.is_authenticated:
        try:
            employee = Employee.objects.get(username=request.user.username)
            achievements = EmployeeAchievement.objects.filter(employee=employee)
            available_tests = Test.objects.all()  # Получаем все доступные тесты
            if available_tests.exists():
                required_experience = Test.required_experience
                required_karma_percentage = Test.required_karma_percentage
            return render(request, 'user_profile.html', {'employee': employee, 'achievements': achievements, 'available_tests': available_tests})
        except Employee.DoesNotExist:
            return HttpResponse("Employee not found")
    else:
        return HttpResponse("Please log in")



def test_detail(request, test_id):
    test = get_object_or_404(Test, pk=test_id)
    questions = test.testquestion_set.all()
    return render(request, 'test_detail.html', {'test': test})

def success_view(request):
    # Получаем текущего аутентифицированного пользователя
    return render(request, 'success.html', )

class RegisterAPIView(APIView):
    @transaction.atomic
    def post(self, request):
        serializer = EmployeeRegSerializer(data=request.data)
        if serializer.is_valid():
            # Создание пользователя
            username = serializer.validated_data['email'].split('@')[0]
            password = User.objects.make_random_password()
            user = User.objects.create_user(username=username, password=password)

            # Создание сотрудника, связанного с пользователем
            employee_data = {**serializer.validated_data, 'username': username, 'password': password}
            employee = Employee.objects.create(**employee_data)

            # Сохранение сгенерированного пароля в сессии
            request.session['generated_password'] = password

            # Возвращение успешного ответа
            return Response({
                'message': 'Registration successful',
                'generated_password': password
            }, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



def create_question(request):
    if request.method == 'POST':
        question_form = QuestionForm(request.POST)
        answer_forms = [AnswerOptionForm(request.POST, prefix=str(x)) for x in range(4)]  # Четыре варианта ответа

        if question_form.is_valid() and all([form.is_valid() for form in answer_forms]):
            question = question_form.save()  # Сохраняем вопрос
            for form in answer_forms:
                answer = form.save(commit=False)
                answer.question = question  # Привязываем ответ к вопросу
                answer.save()

            return redirect('success')  # Перенаправление на страницу успешного создания

    else:
        question_form = QuestionForm()
        answer_forms = [AnswerOptionForm(prefix=str(x)) for x in range(4)]  # Четыре варианта ответа

    return render(request, 'quest_create.html', {'question_form': question_form, 'answer_forms': answer_forms})
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
        employee = Employee.objects.get(id=user_id)
        serializer = EmployeeSerializer(employee)
        return Response(serializer.data)
    except Employee.DoesNotExist:
        return Response({'error': 'User not found'}, status=404)
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
def get_themes_with_tests(request):
    # Получаем все темы
    themes = Theme.objects.all()

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
            test_info = {
                'test': test.id,
                'name': test.name,
                'required_karma': test.required_karma,
                'min_level': test.min_level,
                'achievement': test.achievement.name if test.achievement else None
            }
            tests_info.append(test_info)

        # Добавляем информацию о текущей теме и ее тестах в список
        theme_with_tests = {
            'theme': theme.name,
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
    # Создаем сериализатор теста
    test_serializer = TestSerializer(data=request.data)

    # Проверяем валидность данных теста
    if not test_serializer.is_valid():
        return Response(test_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Сохраняем тест
    test = test_serializer.save()

    # Получаем данные о блоках из запроса
    blocks_data = request.data.get('blocks', [])

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

@api_view(['POST'])
def manually_check_test(request, employee_id, test_id):
    if request.method == 'POST':
        try:
            employee = Employee.objects.get(id=employee_id)
            test = Test.objects.get(id=test_id)
        except (Employee.DoesNotExist, Test.DoesNotExist):
            return Response({"message": "Employee or Test not found"}, status=status.HTTP_404_NOT_FOUND)

        # Получаем все вопросы из теста
        questions = TestQuestion.objects.filter(test=test)

        # Инициализируем список для хранения информации о каждом ответе
        answers_info = []
        total_questions = 0
        # Проверяем ответы на каждый вопрос
        for question in questions:
            total_questions += 1
            print(total_questions)
            answer_info = {}
            if question.question_type == 'text':
                # Для вопросов с типом 'text' проверяющий самостоятельно оценивает ответ
                # Здесь предполагается, что данные о баллах за ответ передаются в теле запроса
                answer_info['question_number'] = total_questions
                answer_info['submitted_answer'] = request.data.get(str(question.number), "")
                answer_info['manual_score'] = request.data.get(f"{question.number}_score", None)
                answers_info.append(answer_info)
            else:
                # Для остальных типов вопросов ответы сравниваются с правильными ответами из базы данных
                answer_key = f"{total_questions}_answer"
                if answer_key in request.data:
                    submitted_answer_id = int(request.data[answer_key])
                    submitted_answer = AnswerOption.objects.get(id=submitted_answer_id)
                    is_correct = submitted_answer.is_correct
                    answer_info['question_number'] = total_questions
                    answer_info['submitted_answer_number'] = submitted_answer_id
                    answer_info['is_correct'] = is_correct
                    answers_info.append(answer_info)

        # Возвращаем информацию о проверенных ответах
        response_data = {
            "message": "Test manually checked.",
            "answers_info": answers_info
        }
        return Response(response_data, status=status.HTTP_200_OK)
@api_view(['GET'])
def test_attempt_moderation_list(request):
    # Получаем все попытки прохождения тестов на модерации
    test_attempts_moderation = TestAttempt.objects.filter(status=TestAttempt.MODERATION)

    # Сериализуем данные
    serializer = TestAttemptSerializer(test_attempts_moderation, many=True)  # Предположим, что у вас есть соответствующий сериализатор

    # Возвращаем ответ с данными
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
def update_test_attempt_status(request, test_attempt_id):
    if request.method == 'POST':
        try:
            test_attempt = TestAttempt.objects.get(id=test_attempt_id)
        except TestAttempt.DoesNotExist:
            return JsonResponse({"message": "TestAttempt not found"}, status=404)

        # Проверяем, что это попытка прохождения теста, которая находится на модерации
        if test_attempt.status != TestAttempt.MODERATION:
            return JsonResponse({"message": "TestAttempt is not in moderation"}, status=400)

        # Получаем данные о баллах за каждый вопрос
        text_questions_score = request.data.get("text_questions_score", {})

        # Итерируемся по ключам словаря submitted_questions (айдишникам вопросов)
        total_score = 0
        # Преобразовать строку в словарь
        submitted_questions_dict = ast.literal_eval(test_attempt.submitted_questions)

        # Теперь можно использовать .items() для итерации по элементам словаря
        for question_id, question_text in submitted_questions_dict.items():
            # Получаем объект вопроса по его айдишнику
            try:
                question = TestQuestion.objects.get(id=question_id)
            except TestQuestion.DoesNotExist:
                return JsonResponse({"message": f"Question with id {question_id} not found"}, status=404)

            # Получаем баллы за вопрос
            question_points = question.points

            # Если для этого вопроса были выставлены баллы в запросе, учитываем их
            if str(question_id) in text_questions_score:
                score_from_request = int(text_questions_score[str(question_id)])
                # Ограничиваем баллы по максимальному количеству баллов за вопрос
                question_points = min(question_points, score_from_request)

            # Добавляем баллы за текущий вопрос к общему счету
            total_score += question_points

        # Обновляем статус в зависимости от набранных баллов
        if total_score >= test_attempt.test.passing_score:
            test_attempt.status = TestAttempt.PASSED
        else:
            test_attempt.status = TestAttempt.FAILED

        # Сохраняем обновленный объект TestAttempt
        test_attempt.save()

        return JsonResponse({"message": "TestAttempt status updated successfully", "total_score": total_score},
                            status=200)
@api_view(['POST'])
def start_test(request, employee_id, test_id):
    if request.method == 'POST':
        try:
            employee = Employee.objects.get(id=employee_id)
            test = Test.objects.get(id=test_id)
        except (Employee.DoesNotExist, Test.DoesNotExist):
            return Response({"message": "Employee or Test not found"}, status=status.HTTP_404_NOT_FOUND)

        # Создаем объект TestAttempt для отслеживания попытки прохождения теста
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

        test_attempt = TestAttempt.objects.filter(employee=employee, test=test,
                                                  status=TestAttempt.IN_PROGRESS).order_by('-start_time').last()

        if not test_attempt:
            return Response({"message": "Test attempt not found"}, status=status.HTTP_404_NOT_FOUND)

        questions = TestQuestion.objects.filter(test=test)
        correct_answers_count = 0
        total_questions = 0
        max_score = 0
        score = 0  # Инициализируем переменную для подсчета баллов

        answers_info = []

        submitted_answers = {}  # Словарь для хранения ответов сотрудника
        submitted_questions = {}  # Словарь для хранения вопросов

        for question_number, question in enumerate(questions, start=1):
            total_questions += 1
            question_text = question.question_text
            answer_options = [{'option_number': index + 1, 'option_text': option.option_text, 'is_correct': option.is_correct} for index, option in enumerate(question.answer_options.all())]
            max_score += question.points

            answer_key = str(question_number)
            if answer_key in request.data:
                submitted_answer = request.data[answer_key]
                submitted_answers[question_text] = submitted_answer  # Сохраняем ответ сотрудника
                submitted_questions[question_text] = question_text  # Сохраняем текст вопроса

                if question.question_type == 'single':
                    submitted_answer_number = int(submitted_answer)
                    if submitted_answer_number <= len(answer_options):
                        submitted_answer_option = answer_options[submitted_answer_number - 1]
                        is_correct = submitted_answer_option['is_correct']
                        if is_correct:
                            correct_answers_count += 1
                            # Добавляем количество баллов за правильный ответ к общему счету
                            score += question.points
                        answer_info = {
                            "question_text": question_text,
                            "is_correct": is_correct,
                            "answer_options": []
                        }
                        for option in answer_options:
                            option_info = {
                                "option_number": option["option_number"],
                                "option_text": option["option_text"],
                                "submitted_answer": option["option_number"] == submitted_answer_number,
                                "correct_options": option["is_correct"]
                            }
                            answer_info["answer_options"].append(option_info)

                        # Включаем пояснение в блок ответа
                        explanation = question.explanation
                        if explanation:
                            answer_info["explanation"] = explanation
                        answers_info.append(answer_info)
                    else:
                        answer_info = {
                            "question_text": question_text,
                            "submitted_answer": submitted_answer,
                            "is_correct": False,
                            "answer_options": [{option['option_number']: option['option_text']} for option in answer_options]
                        }
                        answers_info.append(answer_info)
                elif question.question_type == 'text':
                    # Для вопросов типа "text" просто проверяем, есть ли ответ, но не изменяем score
                    if submitted_answer:
                        correct_answers_count += 1
                        is_correct = True
                    else:
                        is_correct = False
                    answer_info = {
                        "question_text": question_text,
                        "submitted_answer": submitted_answer,
                        "is_correct": is_correct,
                        "answer_options": [{option['option_number']: option['option_text']} for option in answer_options]
                    }
                    if not is_correct:
                        correct_options = [option['option_number'] for option in answer_options if option['is_correct']]
                        answer_info["correct_options"] = correct_options
                    answers_info.append(answer_info)
                elif question.question_type == 'multiple':
                    # Для вопросов с множественным выбором проверяем все предоставленные ответы
                    if isinstance(submitted_answer, int):
                        submitted_answer = [
                            submitted_answer]  # Если только один вариант был выбран, преобразуем его в список
                    submitted_answer_numbers = [int(answer) for answer in submitted_answer]
                    correct_option_numbers = [index + 1 for index, option in enumerate(answer_options) if
                                              option['is_correct']]

                    # Проверяем, содержатся ли в предоставленных ответах все правильные варианты и не содержатся ли неправильные
                    is_correct = set(submitted_answer_numbers) == set(correct_option_numbers) and \
                                 all(option <= len(answer_options) for option in submitted_answer_numbers)

                    if is_correct:
                        correct_answers_count += 1
                        # Добавляем количество баллов за правильный ответ к общему счету
                        score += question.points
                    answer_info = {
                        "question_text": question_text,
                        "submitted_answer": submitted_answer_numbers,
                        "is_correct": is_correct,
                        "answer_options": []
                    }
                    for option in answer_options:
                        option_info = {
                            "option_number": option["option_number"],
                            "option_text": option["option_text"],
                            "submitted_answer": option["option_number"] in submitted_answer_numbers,
                            "correct_options": option["is_correct"]
                        }
                        answer_info["answer_options"].append(option_info)

                    if not is_correct:
                        correct_options = [option['option_number'] for option in answer_options if option['is_correct']]
                        answer_info["correct_options"] = correct_options
                    answers_info.append(answer_info)

        # Обновляем score в test_attempt
        test_attempt.score = score
        test_attempt.end_time = timezone.now()  # Устанавливаем end_time
        test_attempt.save()

        # Сохраняем ответы сотрудника и вопросы в test_attempt
        test_attempt.submitted_answers = submitted_answers
        test_attempt.submitted_questions = submitted_questions
        test_attempt.save()

        # Подготавливаем данные для вывода
        response_data = {
            "Набранное количество баллов": score,
            "Максимальное количество баллов": max_score,
            "answers_info": answers_info
        }

        return Response(response_data, status=status.HTTP_200_OK)

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

    from rest_framework import generics

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
