#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
conductor/urls.py - <+description+>
"""

from django.conf.urls import url

from . import views

app_name = 'conductor'
urlpatterns = [
    url(r'^agents/add$', views.add_agent, name='add_agent'),
    url(r'^agents/del$', views.del_agent, name='del_agent'),
    url(r'^agents/list$', views.list_agents, name='list_agents'),
    url(r'^jobs/add$', views.add_job, name='add_job'),
    url(r'^jobs/del$', views.del_job, name='del_job'),
    url(r'^jobs/list$', views.list_jobs, name='list_jobs'),
    url(r'^jobs/install$', views.install_job, name='install_job'),
    url(r'^jobs/uninstall$', views.uninstall_job, name='uninstall_job'),
    url(r'^(?P<ip_address>(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))/jobs/list$',
        views.list_installed_jobs, name='list_installed_jobs'),
    url(r'^instances/start$', views.start_instance, name='start_instance'),
    url(r'^instances/stop$', views.stop_instance, name='stop_instance'),
    url(r'^instances/restart$', views.restart_instance, name='restart_instance'),
    url(r'^instances/status$', views.status_instance, name='status_instance'),
    url(r'^instances/list$', views.list_instances_per_agent,
        name='list_instances_per_agent'),
    url(r'^(?P<ip_address>(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))/instances/list$',
        views.list_instances, name='list_instances'),
]

