#!/usr/bin/env python 
# -*- coding: utf-8 -*-

""" 
   OpenBACH is a generic testbed able to control/configure multiple
   network/physical entities (under test) and collect data from them. It is
   composed of an Auditorium (HMIs), a Controller, a Collector and multiple
   Agents (one for each network entity that wants to be tested).
   
   
   Copyright © 2016 CNES
   
   
   This file is part of the OpenBACH testbed.
   
   
   OpenBACH is a free software : you can redistribute it and/or modify it under the
   terms of the GNU General Public License as published by the Free Software
   Foundation, either version 3 of the License, or (at your option) any later
   version.
   
   This program is distributed in the hope that it will be useful, but WITHOUT
   ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or FITNESS
   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
   details.
   
   You should have received a copy of the GNU General Public License along with
   this program. If not, see http://www.gnu.org/licenses/.
   
   
   
   @file     urls.py
   @brief    The URL available for the user (throw the frontend)
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


from django.conf.urls import url

from . import views

app_name = 'openbach_django'
urlpatterns = [
    url(r'^agents/add$', views.install_agent, name='install_agent'),
    url(r'^agents/del$', views.uninstall_agent, name='uninstall_agent'),
    url(r'^agents/list$', views.list_agents, name='list_agents'),
    url(r'^agents/status$', views.status_agents, name='status_agents'),

    url(r'^jobs/add$', views.add_job, name='add_job'),
    url(r'^jobs/del$', views.del_job, name='del_job'),
    url(r'^jobs/list$', views.list_jobs, name='list_jobs'),
    url(r'^jobs/help$', views.get_job_help, name='get_job_help'),
    url(r'^jobs/stats$', views.get_job_stats, name='get_job_stats'),

    url(r'^jobs/install$', views.install_jobs, name='install_jobs'),
    url(r'^jobs/uninstall$', views.uninstall_jobs, name='uninstall_jobs'),
    url(r'^jobs/installed_list$', views.list_installed_jobs,
        name='list_installed_jobs'),
    url(r'^jobs/status$', views.status_jobs, name='status_jobs'),
    url(r'^jobs/log_severity', views.set_job_log_severity,
        name='set_job_log_severity'),
    url(r'^jobs/stat_policy', views.set_job_stat_policy,
        name='set_job_stat_policy'),
    url(r'^file/push$', views.push_file, name='push_file'),

    url(r'^instances/start$', views.start_job_instance, name='start_job_instance'),
    url(r'^instances/stop$', views.stop_job_instance, name='stop_job_instance'),
    url(r'^instances/restart$', views.restart_job_instance, name='restart_job_instance'),
    url(r'^instances/status$', views.status_job_instance, name='status_job_instance'),
    url(r'^instances/list$', views.list_job_instances, name='list_job_instances'),
]

