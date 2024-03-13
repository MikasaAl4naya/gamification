from django.contrib import admin

from main.models import Employee, Achievement, Classifications, Request

# Register your models here.
admin.site.register(Employee)
admin.site.register(Achievement)
admin.site.register(Classifications)
admin.site.register(Request)
