from django.contrib import admin

from main.models import *

admin.site.register(Achievement)
admin.site.register(Classifications)
admin.site.register(Test)
admin.site.register(TestAttempt)
admin.site.register(TestQuestion)
admin.site.register(Theme)
admin.site.register(Permission)
admin.site.register(FilePath)
admin.site.register(Feedback)
admin.site.register(SystemSetting)
admin.site.register(LevelTitle)
admin.site.register(PasswordPolicy)
admin.site.register(EmployeeActionLog)
admin.site.register(Item)
admin.site.register(ShiftHistory)
admin.site.register(Template)
admin.site.register(ComplexityThresholds)

@admin.register(Request)
class RequestAdmin(admin.ModelAdmin):
    # Определяем поля, которые будут отображаться в списке объектов
    list_display = ('number', 'support_operator_full_name', 'classification', 'date')
    # Определяем, по каким полям можно выполнять поиск
    search_fields = ('support_operator__first_name', 'support_operator__last_name', 'classification__name')
    # Определяем, по каким полям можно фильтровать записи
    list_filter = ('classification', 'date')

    def support_operator_full_name(self, obj):
        # Метод для отображения ФИО сотрудника
        return f"{obj.support_operator.first_name} {obj.support_operator.last_name}"
    support_operator_full_name.short_description = 'Сотрудник'



@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'is_active')


@admin.register(KarmaSettings)
class OperationSettingsAdmin(admin.ModelAdmin):
    list_display = ('operation_type', 'level', 'karma_change', 'experience_change')
    list_filter = ('operation_type', 'level')
    search_fields = ('operation_type', 'level')

    def get_list_display(self, request):
        # Если тип операции - не фидбек, не показываем уровень
        if any([self.get_queryset(request).filter(operation_type__in=[KarmaSettings.PRAISE, KarmaSettings.COMPLAINT]).exists()]):
            return ('operation_type', 'level', 'karma_change', 'experience_change')
        return ('operation_type', 'karma_change', 'experience_change')

    def get_list_filter(self, request):
        # Если тип операции - не фидбек, не фильтруем по уровню
        if any([self.get_queryset(request).filter(operation_type__in=[KarmaSettings.PRAISE, KarmaSettings.COMPLAINT]).exists()]):
            return ('operation_type', 'level')
        return ('operation_type',)

    def get_search_fields(self, request):
        # Если тип операции - не фидбек, не ищем по уровню
        if any([self.get_queryset(request).filter(operation_type__in=[KarmaSettings.PRAISE, KarmaSettings.COMPLAINT]).exists()]):
            return ('operation_type', 'level')
        return ('operation_type',)
class EmployeeAchievementAdmin(admin.ModelAdmin):
    list_display = ('employee', 'achievement', 'progress', 'level')
    search_fields = ('employee__first_name', 'employee__last_name', 'achievement__description')
    list_filter = ('achievement', 'level')

admin.site.register(EmployeeAchievement, EmployeeAchievementAdmin)