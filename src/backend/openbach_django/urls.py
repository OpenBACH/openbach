#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
openbach_django/urls.py - <+description+>
"""

from django.conf.urls import url

from . import views

app_name = 'openbach_django'
urlpatterns = [
    url(r'^agents/add$', views.add_agent, name='add_agent'),
    url(r'^agents/del$', views.del_agent, name='del_agent'),
    url(r'^agents/list$', views.list_agents, name='list_agents'),
    url(r'^agents/status$', views.status_agents, name='status_agents'),

    url(r'^jobs/add$', views.add_job, name='add_job'),
    url(r'^jobs/del$', views.del_job, name='del_job'),
    url(r'^jobs/list$', views.list_jobs_url, name='list_jobs_url'),

    url(r'^jobs/install$', views.install_jobs, name='install_jobs'),
    url(r'^jobs/uninstall$', views.uninstall_jobs, name='uninstall_jobs'),
    url(r'^jobs/status$', views.status_jobs, name='status_jobs'),
    url(r'^jobs/log_severity', views.update_job_log_severity,
        name='update_job_log_severity'),
    url(r'^jobs/stat_policy', views.update_job_stat_policy,
        name='update_job_stat_policy'),

    url(r'^instances/start$', views.start_instance, name='start_instance'),
    url(r'^instances/stop$', views.stop_instance, name='stop_instance'),
    url(r'^instances/restart$', views.restart_instance, name='restart_instance'),
    url(r'^instances/status$', views.status_instance, name='status_instance'),
    url(r'^instances/list$', views.list_instances, name='list_instances'),
]

