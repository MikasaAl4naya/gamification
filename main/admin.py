from django.contrib import admin

from main.models import *

# Register your models here.
admin.site.register(Employee)
admin.site.register(Achievement)
admin.site.register(Classifications)
admin.site.register(Request)
admin.site.register(Test)
admin.site.register(TestAttempt)
admin.site.register(TestQuestion)
admin.site.register(Theme)
admin.site.register(Permission)
admin.site.register(FilePath)
admin.site.register(Feedback)
admin.site.register(SystemSetting)


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
