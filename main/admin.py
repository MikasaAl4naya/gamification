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
class KarmaSettingsAdmin(admin.ModelAdmin):
    list_display = ('feedback_type', 'level', 'karma_change')
    list_filter = ('feedback_type', 'level')
    search_fields = ('feedback_type', 'level')