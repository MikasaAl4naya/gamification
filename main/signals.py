# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from .models import Request, Achievement, EmployeeAchievement
#
# @receiver(post_save, sender=Request)
# def update_achievement_progress(sender, instance, **kwargs):
#     if instance.status == 'Completed':
#         try:
#             achievement = Achievement.objects.get(request_type=instance.classification)
#         except Achievement.DoesNotExist:
#             return
#
#         employee_achievement, created = EmployeeAchievement.objects.get_or_create(
#             employee=instance.responsible,
#             achievement=achievement
#         )
#
#         employee_achievement.progress += 1
#
#         if employee_achievement.progress >= achievement.required_count:
#             achievement.level_up()
#             employee_achievement.progress = 0
#
#         employee_achievement.save()
#         print('Updated achievement')
