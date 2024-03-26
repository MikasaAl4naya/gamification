from .models import Employee, Request, Achievement, TestQuestion, AnswerOption
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm


class EmployeeRegistrationForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)
    email = forms.EmailField(max_length=254)
    position = forms.CharField(max_length=100)

    class Meta:
        model = Employee
        fields = ['first_name', 'last_name', 'email', 'position']


    def save(self, commit=True):
        user = super(EmployeeRegistrationForm, self).save(commit=False)
        user.set_password(User.objects.make_random_password())  # Генерация случайного пароля
        if commit:
            user.save()
        return user

class AchievementForm(forms.ModelForm):
    class Meta:
        model = Achievement
        fields = ['name', 'description', 'request_type', 'required_count', 'reward_experience', 'reward_currency', 'image']

class RequestForm(forms.ModelForm):
    class Meta:
        model = Request
        fields = ['classification', 'responsible', 'status']

class EmployeeAuthenticationForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)



class QuestionForm(forms.ModelForm):
    class Meta:
        model = TestQuestion
        fields = ['test', 'question_text', 'question_type']  # Добавляем поле 'test'

class AnswerOptionForm(forms.ModelForm):
    class Meta:
        model = AnswerOption
        fields = ['option_text', 'is_correct']



