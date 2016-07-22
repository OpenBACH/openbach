from django.contrib import admin

from .models import Agent, Job, Installed_Job, Job_Instance, Watch, Job_Keyword
from .models import Available_Statistic, Required_Job_Argument, Optional_Job_Argument
from .models import Required_Job_Argument_Instance, Optional_Job_Argument_Instance
from .models import Job_Argument_Value


class AdminJobInstances(admin.ModelAdmin):
    list_display = ('__str__', 'is_stopped')

admin.site.register(Agent)
admin.site.register(Job)
admin.site.register(Installed_Job)
admin.site.register(Job_Instance, AdminJobInstances)
admin.site.register(Watch)
admin.site.register(Job_Keyword)
admin.site.register(Available_Statistic)
admin.site.register(Required_Job_Argument)
admin.site.register(Optional_Job_Argument)
admin.site.register(Required_Job_Argument_Instance)
admin.site.register(Optional_Job_Argument_Instance)
admin.site.register(Job_Argument_Value)
