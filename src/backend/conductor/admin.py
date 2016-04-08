from django.contrib import admin

from .models import Agent, Job, Installed_Job, Instance

admin.site.register(Agent)
admin.site.register(Job)
admin.site.register(Installed_Job)
admin.site.register(Instance)
