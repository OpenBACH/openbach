from django.contrib import admin

from .models import *


class AdminJobInstances(admin.ModelAdmin):
    list_display = ('__str__', 'is_stopped')

admin.site.register(Agent)
admin.site.register(Job)
admin.site.register(Installed_Job)
admin.site.register(Job_Instance, AdminJobInstances)
admin.site.register(Watch)
admin.site.register(Job_Keyword)
admin.site.register(Statistic)
admin.site.register(Required_Job_Argument)
admin.site.register(Optional_Job_Argument)
admin.site.register(Required_Job_Argument_Instance)
admin.site.register(Optional_Job_Argument_Instance)
admin.site.register(Job_Argument_Value)
admin.site.register(Statistic_Instance)
admin.site.register(Scenario)
admin.site.register(Scenario_Argument)
admin.site.register(Openbach_Function)
admin.site.register(Openbach_Function_Argument)
admin.site.register(Scenario_Instance)
admin.site.register(Scenario_Argument_Instance)
admin.site.register(Openbach_Function_Instance)
admin.site.register(Wait_For)
admin.site.register(Wait_For_Launched)
admin.site.register(Wait_For_Finished)
admin.site.register(Openbach_Function_Argument_Instance)
