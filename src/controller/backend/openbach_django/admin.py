from django.contrib import admin

from .models import Agent, Job, Installed_Job, Job_Instance, Watch
from .models import Job_Keyword, Available_Statistic


class AdminJobInstances(admin.ModelAdmin):
    list_display = ('__str__', 'is_stopped')

admin.site.register(Agent)
admin.site.register(Job)
admin.site.register(Installed_Job)
admin.site.register(Job_Instance, AdminJobInstances)
admin.site.register(Watch)
admin.site.register(Job_Keyword)
admin.site.register(Available_Statistic)
