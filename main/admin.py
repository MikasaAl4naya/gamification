from django.contrib import admin

from main.models import Employee, Achievement, Classifications, Request, Test, TestAttempt, TestQuestion, Theme

# Register your models here.
admin.site.register(Employee)
admin.site.register(Achievement)
admin.site.register(Classifications)
admin.site.register(Request)
admin.site.register(Test)
admin.site.register(TestAttempt)
admin.site.register(TestQuestion)
admin.site.register(Theme)