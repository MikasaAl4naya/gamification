from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.checks import messages
from django.http import HttpResponse
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.crypto import get_random_string
from django.contrib.auth.tokens import default_token_generator
from .models import Achievement, Employee, EmployeeAchievement
from django.shortcuts import render, redirect
from .forms import AchievementForm, RequestForm, EmployeeRegistrationForm, EmployeeAuthenticationForm
from django.shortcuts import redirect

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import LoginSerializer, EmployeeSerializer, EmployeeRegSerializer  # Импортируем сериализатор

from django.contrib.auth import authenticate


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
            return render(request, 'user_profile.html', {'employee': employee, 'achievements': achievements})
        except Employee.DoesNotExist:
            return HttpResponse("Employee not found")
    else:
        return HttpResponse("Please log in")


def success_view(request):
    # Получаем текущего аутентифицированного пользователя
    user = request.user
    # Ищем сотрудника с таким же логином как у текущего пользователя
    try:
        employee = Employee.objects.get(username=user.username)
    except Employee.DoesNotExist:
        # Если сотрудник с таким логином не найден, делайте необходимые действия
        pass
    print(employee.first_name, employee.last_name, employee.email, employee.username)
    return render(request, 'success.html', {'employee': employee})

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


