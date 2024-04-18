from django.contrib.auth import login, logout
from django.core.checks import messages
from django.http import HttpResponse
from django.contrib.auth.models import User
from rest_framework.generics import RetrieveAPIView
from .models import Achievement, Employee, EmployeeAchievement, TestQuestion, AnswerOption, Test, AcoinTransaction, \
    Acoin, TestAttempt, Theme
from django.shortcuts import get_object_or_404, render, redirect
from .forms import AchievementForm, RequestForm, EmployeeRegistrationForm, EmployeeAuthenticationForm, QuestionForm, \
    AnswerOptionForm
from rest_framework.decorators import api_view
from .serializers import TestQuestionSerializer, AnswerOptionSerializer, TestSerializer, AcoinTransactionSerializer, \
    AcoinSerializer, ThemeWithTestsSerializer, AchievementSerializer, RequestSerializer, ThemeSerializer
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

    # Получаем все вопросы для данного теста
    questions = TestQuestion.objects.filter(test=test).order_by('id')

    # Сериализуем данные вопросов
    question_serializer = TestQuestionSerializer(questions, many=True)


    # Создаем окончательный ответ, включающий данные теста, вопросов и ответов
    response_data = {
        'test': test_serializer.data,
        'questions': question_serializer.data

    }

    return Response(response_data)
@api_view(['GET'])
def get_themes_with_tests(request):
    # Получаем все тесты
    tests = Test.objects.all()

    # Создаем словарь для хранения тем и связанных с ними тестов
    themes_with_tests = {}

    # Проходимся по всем тестам и добавляем их к соответствующим темам в словаре
    for test in tests:
        theme = test.theme
        if theme not in themes_with_tests:
            themes_with_tests[theme] = []
        themes_with_tests[theme].append({
            'name': test.name,
            'required_karma': test.required_karma,
            'min_level': test.min_level,
            'achievement': test.achievement.name if test.achievement else None
        })

    # Преобразуем словарь в список объектов для сериализации
    themes_with_tests_list = [{'theme': theme, 'tests': tests} for theme, tests in themes_with_tests.items()]

    return Response(themes_with_tests_list)
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
        serializer = AchievementSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
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



@api_view(['POST'])
def complete_test(request, employee_id, test_id):
    if request.method == 'POST':
        try:
            employee = Employee.objects.get(id=employee_id)
            test = Test.objects.get(id=test_id)
        except (Employee.DoesNotExist, Test.DoesNotExist):
            return Response({"message": "Employee or Test not found"}, status=status.HTTP_404_NOT_FOUND)

        # Получаем все вопросы из теста
        questions = TestQuestion.objects.filter(test=test)

        # Инициализируем счетчик правильных ответов и общее количество вопросов
        correct_answers_count = 0
        total_questions = 0

        # Инициализируем словарь для хранения номеров ответов на вопросы
        answer_options = {}

        # Заполняем словарь с номерами ответов для каждого вопроса
        for question in questions:
            # Получаем все ответы на текущий вопрос и преобразуем их айдишники в список
            answer_ids = list(question.answer_options.values_list('id', flat=True))
            # Присваиваем номера ответам, начиная с 1
            answer_numbers = list(range(1, len(answer_ids) + 1))
            # Соединяем айдишники с соответствующими номерами
            answer_options[question.id] = dict(zip(answer_numbers, answer_ids))

        # Проверяем ответы на каждый вопрос
        for question_number, question in enumerate(questions, start=1):
            total_questions += 1
            # Проверяем, есть ли ответ на текущий вопрос в запросе
            answer_key = str(question_number)
            if answer_key in request.data:
                submitted_answer_number = request.data[answer_key]
                # Проверяем, содержится ли номер ответа в списке номеров для текущего вопроса
                if submitted_answer_number in answer_options[question.id]:
                    submitted_answer_id = answer_options[question.id][submitted_answer_number]
                    submitted_answer = AnswerOption.objects.get(id=submitted_answer_id)
                    # Проверяем, является ли ответ сотрудника правильным
                    if submitted_answer.is_correct:
                        correct_answers_count += 1
        print(correct_answers_count,"correct answers")
        # Рассчитываем процент правильных ответов
        if total_questions > 0:
            correct_answers_percentage = (correct_answers_count / total_questions) * 100
        else:
            correct_answers_percentage = 0

        # Определяем, прошел ли сотрудник тест
        if correct_answers_percentage >= test.passing_score:
            test_status = TestAttempt.PASSED
            message = "Test passed successfully."
        else:
            test_status = TestAttempt.FAILED
            message = "Test failed."

        # Создаем объект TestAttempt для отслеживания попытки прохождения теста
        test_attempt = TestAttempt.objects.create(employee=employee, test=test, status=test_status)

        # Возвращаем результат прохождения теста
        return Response({"message": message, "correct_answers_percentage": correct_answers_percentage},
                        status=status.HTTP_200_OK)




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
