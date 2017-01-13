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



   @file     0002_create_openbach_functions.py
   @brief    File that will create the openbach functions in the DB during the
             initialization
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


from __future__ import unicode_literals

from django.db import migrations


def create_openbach_functions(apps, schema_editor):
    Openbach_Function = apps.get_model("openbach_django", "Openbach_Function")
    Openbach_Function_Argument = apps.get_model("openbach_django",
                                                "Openbach_Function_Argument")

    # install_agent
    install_agent = Openbach_Function(name='install_agent')
    install_agent.save()
    Openbach_Function_Argument(name='address', description='Address of the new'
                               ' Agent', type='ip',
                               openbach_function=install_agent).save()
    Openbach_Function_Argument(name='collector', description='Address of the '
                               'associated Collector', type='ip',
                               openbach_function=install_agent).save()
    Openbach_Function_Argument(name='username', description='Username of the'
                               ' new Agent', type='str',
                               openbach_function=install_agent).save()
    Openbach_Function_Argument(name='password', description='Password of the'
                               ' new Agent', type='str',
                               openbach_function=install_agent).save()
    Openbach_Function_Argument(name='name', description='Name of the new Agent',
                               type='str',
                               openbach_function=install_agent).save()

    # uninstall_agent
    uninstall_agent = Openbach_Function(name='uninstall_agent')
    uninstall_agent.save()
    Openbach_Function_Argument(name='address', description='Address of the new'
                               ' Agent', type='ip',
                               openbach_function=uninstall_agent).save()

    # list_agents
    list_agents = Openbach_Function(name='list_agents')
    list_agents.save()
    Openbach_Function_Argument(name='update', description='', type='bool',
                               openbach_function=list_agents).save()

    # status_agents
    status_agents = Openbach_Function(name='status_agents')
    status_agents.save()
    Openbach_Function_Argument(name='addresses', description='', type='list',
                               openbach_function=status_agents).save()
    Openbach_Function_Argument(name='update', description='', type='bool',
                               openbach_function=status_agents).save()

    # add_job
    add_job = Openbach_Function(name='add_job')
    add_job.save()
    Openbach_Function_Argument(name='name', description='', type='str',
                               openbach_function=add_job).save()
    Openbach_Function_Argument(name='path', description='', type='str',
                               openbach_function=add_job).save()

    # del_job
    del_job = Openbach_Function(name='del_job')
    del_job.save()
    Openbach_Function_Argument(name='name', description='', type='str',
                    openbach_function=del_job).save()

    # list_jobs
    list_jobs = Openbach_Function(name='list_jobs')
    list_jobs.save()
    Openbach_Function_Argument(name='verbosity', description='', type='int',
                               openbach_function=list_jobs).save()

    # get_job_stats
    get_job_stats = Openbach_Function(name='get_job_stats')
    get_job_stats.save()
    Openbach_Function_Argument(name='name', description='', type='str',
                               openbach_function=get_job_stats).save()
    Openbach_Function_Argument(name='verbosity', description='', type='int',
                               openbach_function=get_job_stats).save()

    # get_job_help
    get_job_help = Openbach_Function(name='get_job_help')
    get_job_help.save()
    Openbach_Function_Argument(name='name', description='', type='str',
                               openbach_function=get_job_help).save()

    # install_jobs
    install_jobs = Openbach_Function(name='install_jobs')
    install_jobs.save()
    Openbach_Function_Argument(name='addresses', description='', type='list',
                               openbach_function=install_jobs).save()
    Openbach_Function_Argument(name='names', description='', type='list',
                               openbach_function=install_jobs).save()
    Openbach_Function_Argument(name='severity', description='', type='int',
                               openbach_function=install_jobs).save()
    Openbach_Function_Argument(name='local_severity', description='',
                               type='int',
                               openbach_function=install_jobs).save()

    # install_jobs
    uninstall_jobs = Openbach_Function(name='uninstall_jobs')
    uninstall_jobs.save()
    Openbach_Function_Argument(name='addresses', description='', type='list',
                               openbach_function=uninstall_jobs).save()
    Openbach_Function_Argument(name='names', description='', type='list',
                               openbach_function=uninstall_jobs).save()

    # list_installed_jobs
    list_installed_jobs = Openbach_Function(name='list_installed_jobs')
    list_installed_jobs.save()
    Openbach_Function_Argument(name='address', description='', type='ip',
                               openbach_function=list_installed_jobs).save()
    Openbach_Function_Argument(name='update', description='', type='bool',
                               openbach_function=list_installed_jobs).save()
    Openbach_Function_Argument(name='verbosity', description='', type='int',
                               openbach_function=list_installed_jobs).save()

    # status_jobs
    status_jobs = Openbach_Function(name='status_jobs')
    status_jobs.save()
    Openbach_Function_Argument(name='addresses', description='', type='list',
                               openbach_function=status_jobs).save()

    # push_file
    push_file = Openbach_Function(name='push_file')
    push_file.save()
    Openbach_Function_Argument(name='local_path', description='', type='str',
                               openbach_function=push_file).save()
    Openbach_Function_Argument(name='remote_path', description='', type='str',
                               openbach_function=push_file).save()
    Openbach_Function_Argument(name='agent_ip', description='', type='ip',
                               openbach_function=push_file).save()

    # start_job_instance
    start_job_instance = Openbach_Function(name='start_job_instance')
    start_job_instance.save()
    Openbach_Function_Argument(name='agent_ip', description='', type='ip',
                               openbach_function=start_job_instance).save()
    Openbach_Function_Argument(name='job_name', description='', type='str',
                               openbach_function=start_job_instance).save()
    Openbach_Function_Argument(name='instance_args', description='', type='json',
                               openbach_function=start_job_instance).save()
    Openbach_Function_Argument(name='offset', description='', type='int',
                               openbach_function=start_job_instance).save()
    Openbach_Function_Argument(name='interval', description='', type='int',
                               openbach_function=start_job_instance).save()

    # stop_job_instance
    stop_job_instance = Openbach_Function(name='stop_job_instance')
    stop_job_instance.save()
    Openbach_Function_Argument(name='openbach_function_ids', description='',
                               type='list',
                               openbach_function=stop_job_instance).save()
    Openbach_Function_Argument(name='date', description='', type='str',
                               openbach_function=stop_job_instance).save()

    # restart_job_instance
    restart_job_instance = Openbach_Function(name='restart_job_instance')
    restart_job_instance.save()
    Openbach_Function_Argument(name='instance_id', description='', type='int',
                               openbach_function=restart_job_instance).save()
    Openbach_Function_Argument(name='instance_args', description='', type='json',
                               openbach_function=restart_job_instance).save()
    Openbach_Function_Argument(name='date', description='', type='str',
                               openbach_function=restart_job_instance).save()
    Openbach_Function_Argument(name='interval', description='', type='int',
                               openbach_function=restart_job_instance).save()

    # watch_job_instance
    watch_job_instance = Openbach_Function(name='watch_job_instance')
    watch_job_instance.save()
    Openbach_Function_Argument(name='instance_id', description='', type='int',
                               openbach_function=watch_job_instance).save()
    Openbach_Function_Argument(name='date', description='', type='str',
                               openbach_function=watch_job_instance).save()
    Openbach_Function_Argument(name='interval', description='', type='int',
                               openbach_function=watch_job_instance).save()
    Openbach_Function_Argument(name='stop', description='', type='str',
                               openbach_function=watch_job_instance).save()

    # status_job_instance
    status_job_instance = Openbach_Function(name='status_job_instance')
    status_job_instance.save()
    Openbach_Function_Argument(name='instance_id', description='', type='int',
                               openbach_function=status_job_instance).save()
    Openbach_Function_Argument(name='verbosity', description='', type='int',
                               openbach_function=status_job_instance).save()
    Openbach_Function_Argument(name='update', description='', type='bool',
                               openbach_function=status_job_instance).save()

    # list_job_instances
    list_job_instances = Openbach_Function(name='list_job_instances')
    list_job_instances.save()
    Openbach_Function_Argument(name='addresses', description='', type='list',
                               openbach_function=list_job_instances).save()
    Openbach_Function_Argument(name='update', description='', type='bool',
                               openbach_function=list_job_instances).save()
    Openbach_Function_Argument(name='verbosity', description='', type='int',
                               openbach_function=list_job_instances).save()

    # set_job_log_severity
    set_job_log_severity = Openbach_Function(name='set_job_log_severity')
    set_job_log_severity.save()
    Openbach_Function_Argument(name='address', description='', type='ip',
                               openbach_function=set_job_log_severity).save()
    Openbach_Function_Argument(name='job_name', description='', type='str',
                               openbach_function=set_job_log_severity).save()
    Openbach_Function_Argument(name='severity', description='', type='int',
                               openbach_function=set_job_log_severity).save()
    Openbach_Function_Argument(name='date', description='', type='str',
                               openbach_function=set_job_log_severity).save()
    Openbach_Function_Argument(name='local_severity', description='',
                               type='int',
                               openbach_function=set_job_log_severity).save()

    # set_job_stat_policy
    set_job_stat_policy = Openbach_Function(name='set_job_stat_policy')
    set_job_stat_policy.save()
    Openbach_Function_Argument(name='address', description='', type='ip',
                               openbach_function=set_job_stat_policy).save()
    Openbach_Function_Argument(name='job_name', description='', type='str',
                               openbach_function=set_job_stat_policy).save()
    Openbach_Function_Argument(name='stat_name', description='', type='str',
                               openbach_function=set_job_stat_policy).save()
    Openbach_Function_Argument(name='storage', description='', type='bool',
                               openbach_function=set_job_stat_policy).save()
    Openbach_Function_Argument(name='broadcast', description='', type='bool',
                               openbach_function=set_job_stat_policy).save()
    Openbach_Function_Argument(name='date', description='', type='str',
                               openbach_function=set_job_stat_policy).save()

    # if
    if_ = Openbach_Function(name='if')
    if_.save()
    Openbach_Function_Argument(name='openbach_functions_true', description='',
                               type='list', openbach_function=if_).save()
    Openbach_Function_Argument(name='openbach_functions_false', description='',
                               type='list', openbach_function=if_).save()

    # while
    while_ = Openbach_Function(name='while')
    while_.save()
    Openbach_Function_Argument(name='openbach_functions_while', description='',
                               type='list', openbach_function=while_).save()
    Openbach_Function_Argument(name='openbach_functions_end', description='',
                               type='list', openbach_function=while_).save()

    # start_scenario_instance
    start_scenario_instance = Openbach_Function(name='start_scenario_instance')
    start_scenario_instance.save()
    Openbach_Function_Argument(name='scenario_name', description='', type='str',
                               openbach_function=start_scenario_instance).save()
    Openbach_Function_Argument(name='arguments', description='', type='json',
                               openbach_function=start_scenario_instance).save()

    # stop_scenario_instance
    stop_scenario_instance = Openbach_Function(name='stop_scenario_instance')
    stop_scenario_instance.save()
    Openbach_Function_Argument(name='openbach_function_id', description='',
                               type='int',
                               openbach_function=stop_scenario_instance).save()


class Migration(migrations.Migration):

    dependencies = [
        ('openbach_django', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_openbach_functions),
    ]
