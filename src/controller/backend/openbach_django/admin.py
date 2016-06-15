from django.contrib import admin

from .models import Agent, Job, Installed_Job, Job_Instance, Watch

admin.site.register(Agent)
admin.site.register(Job)
admin.site.register(Installed_Job)
admin.site.register(Job_Instance)
admin.site.register(Watch)
