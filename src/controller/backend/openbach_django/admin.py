from django.contrib import admin

from .models import *


class AdminInstances(admin.ModelAdmin):
    list_display = ('__str__', 'is_stopped')

class AdminAgent(admin.ModelAdmin):
    exclude = ('password',)

admin.site.register(Agent, AdminAgent)
admin.site.register(Job_Keyword)
admin.site.register(Job)
admin.site.register(Statistic)
admin.site.register(Required_Job_Argument)
admin.site.register(Optional_Job_Argument)
admin.site.register(Installed_Job)
admin.site.register(Statistic_Instance)
admin.site.register(Job_Instance, AdminInstances)
admin.site.register(Required_Job_Argument_Instance)
admin.site.register(Optional_Job_Argument_Instance)
admin.site.register(Job_Argument_Value)
admin.site.register(Watch)
admin.site.register(Openbach_Function)
admin.site.register(Openbach_Function_Argument)
admin.site.register(Scenario)
admin.site.register(Scenario_Argument)
admin.site.register(Scenario_Instance, AdminInstances)
admin.site.register(Scenario_Argument_Instance)
admin.site.register(Operand_Database)
admin.site.register(Operand_Value)
admin.site.register(Operand_Statistic)
admin.site.register(Condition_Or)
admin.site.register(Condition_And)
admin.site.register(Condition_Not)
admin.site.register(Condition_Xor)
admin.site.register(Condition_Equal)
admin.site.register(Condition_Unequal)
admin.site.register(Condition_Below_Or_Equal)
admin.site.register(Condition_Below)
admin.site.register(Condition_Upper_Or_Equal)
admin.site.register(Condition_Upper)
admin.site.register(Openbach_Function_Instance)
admin.site.register(Wait_For_Launched)
admin.site.register(Wait_For_Finished)
admin.site.register(Openbach_Function_Argument_Instance)
