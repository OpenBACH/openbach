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
   
   
   
   @file     0002_create_actions.py
   @brief    File that will create the action ine the DB durint the
             initialization
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


from __future__ import unicode_literals

from django.db import migrations


def create_actions(apps, schema_editor):
    Action = apps.get_model("openbach_django", "Action")
    Action_Argument = apps.get_model("openbach_django", "Action_Argument")

    # install_agent
    install_agent = Action(name='install_agent')
    install_agent.save()
    Action_Argument(name='address', description='Address of the new Agent',
                    type='ip', action=install_agent).save()
    Action_Argument(name='collector', description='Address of the associated'
                    ' Collector',
                    type='ip', action=install_agent).save()
    Action_Argument(name='username', description='Username of the new Agent',
                    type='str', action=install_agent).save()
    Action_Argument(name='password', description='Password of the new Agent',
                    type='str', action=install_agent).save()
    Action_Argument(name='name', description='Name of the new Agent',
                    type='str', action=install_agent).save()

    # uninstall_agent
    uninstall_agent = Action(name='uninstall_agent')
    uninstall_agent.save()
    Action_Argument(name='address', description='Address of the new Agent',
                    type='ip', action=uninstall_agent).save()

    # list_agents
    list_agents = Action(name='list_agents')
    list_agents.save()
    Action_Argument(name='update', description='', type='bool',
                    action=list_agents).save()

    # status_agents
    status_agents = Action(name='status_agents')
    status_agents.save()
    Action_Argument(name='addresses', description='', type='list',
                    action=status_agents).save()

    # add_job
    add_job = Action(name='add_job')
    add_job.save()
    Action_Argument(name='name', description='', type='str',
                    action=add_job).save()
    Action_Argument(name='path', description='', type='str',
                    action=add_job).save()

    # del_job
    del_job = Action(name='del_job')
    del_job.save()
    Action_Argument(name='name', description='', type='str',
                    action=del_job).save()

    # list_jobs
    list_jobs = Action(name='list_jobs')
    list_jobs.save()
    Action_Argument(name='verbosity', description='', type='int',
                    action=list_jobs).save()

    # get_job_stats
    get_job_stats = Action(name='get_job_stats')
    get_job_stats.save()
    Action_Argument(name='name', description='', type='str',
                    action=get_job_stats).save()
    Action_Argument(name='verbosity', description='', type='int',
                    action=get_job_stats).save()

    # get_job_help
    get_job_help = Action(name='get_job_help')
    get_job_help.save()
    Action_Argument(name='name', description='', type='str',
                    action=get_job_help).save()

    # install_jobs
    install_jobs = Action(name='install_jobs')
    install_jobs.save()
    Action_Argument(name='addresses', description='', type='list',
                    action=install_jobs).save()
    Action_Argument(name='names', description='', type='list',
                    action=install_jobs).save()
    Action_Argument(name='severity', description='', type='int',
                    action=install_jobs).save()
    Action_Argument(name='local_severity', description='', type='int',
                    action=install_jobs).save()

    # install_jobs
    uninstall_jobs = Action(name='uninstall_jobs')
    uninstall_jobs.save()
    Action_Argument(name='addresses', description='', type='list',
                    action=uninstall_jobs).save()
    Action_Argument(name='names', description='', type='list',
                    action=uninstall_jobs).save()

    # list_installed_jobs
    list_installed_jobs = Action(name='list_installed_jobs')
    list_installed_jobs.save()
    Action_Argument(name='address', description='', type='ip',
                    action=list_installed_jobs).save()
    Action_Argument(name='update', description='', type='bool',
                    action=list_installed_jobs).save()
    Action_Argument(name='verbosity', description='', type='int',
                    action=list_installed_jobs).save()

    # status_jobs
    status_jobs = Action(name='status_jobs')
    status_jobs.save()
    Action_Argument(name='addresses', description='', type='list',
                    action=status_jobs).save()

    # push_file
    push_file = Action(name='push_file')
    push_file.save()
    Action_Argument(name='local_path', description='', type='str',
                    action=push_file).save()
    Action_Argument(name='remote_path', description='', type='str',
                    action=push_file).save()
    Action_Argument(name='agent_ip', description='', type='ip',
                    action=push_file).save()

    # start_job_instance
    start_job_instance = Action(name='start_job_instance')
    start_job_instance.save()
    Action_Argument(name='agent_ip', description='', type='ip',
                    action=start_job_instance).save()
    Action_Argument(name='job_name', description='', type='str',
                    action=start_job_instance).save()
    Action_Argument(name='instance_args', description='', type='str',
                    action=start_job_instance).save()
    Action_Argument(name='date', description='', type='str',
                    action=start_job_instance).save()
    Action_Argument(name='interval', description='', type='int',
                    action=start_job_instance).save()

    # stop_job_instance
    stop_job_instance = Action(name='stop_job_instance')
    stop_job_instance.save()
    Action_Argument(name='instance_ids', description='', type='list',
                    action=stop_job_instance).save()
    Action_Argument(name='date', description='', type='str',
                    action=stop_job_instance).save()

    # restart_job_instance
    restart_job_instance = Action(name='restart_job_instance')
    restart_job_instance.save()
    Action_Argument(name='instance_id', description='', type='int',
                    action=restart_job_instance).save()
    Action_Argument(name='instance_args', description='', type='str',
                    action=restart_job_instance).save()
    Action_Argument(name='date', description='', type='str',
                    action=restart_job_instance).save()
    Action_Argument(name='interval', description='', type='int',
                    action=restart_job_instance).save()

    # watch_job_instance
    watch_job_instance = Action(name='watch_job_instance')
    watch_job_instance.save()
    Action_Argument(name='instance_id', description='', type='int',
                    action=watch_job_instance).save()
    Action_Argument(name='date', description='', type='str',
                    action=watch_job_instance).save()
    Action_Argument(name='interval', description='', type='int',
                    action=watch_job_instance).save()
    Action_Argument(name='stop', description='', type='str',
                    action=watch_job_instance).save()

    # status_job_instance
    status_job_instance = Action(name='status_job_instance')
    status_job_instance.save()
    Action_Argument(name='instance_id', description='', type='int',
                    action=status_job_instance).save()
    Action_Argument(name='verbosity', description='', type='int',
                    action=status_job_instance).save()
    Action_Argument(name='update', description='', type='bool',
                    action=status_job_instance).save()

    # list_job_instances
    list_job_instances = Action(name='list_job_instances')
    list_job_instances.save()
    Action_Argument(name='addresses', description='', type='list',
                    action=list_job_instances).save()
    Action_Argument(name='update', description='', type='bool',
                    action=list_job_instances).save()
    Action_Argument(name='verbosity', description='', type='int',
                    action=list_job_instances).save()

    # set_job_log_severity
    set_job_log_severity = Action(name='set_job_log_severity')
    set_job_log_severity.save()
    Action_Argument(name='address', description='', type='ip',
                    action=set_job_log_severity).save()
    Action_Argument(name='job_name', description='', type='str',
                    action=set_job_log_severity).save()
    Action_Argument(name='severity', description='', type='int',
                    action=set_job_log_severity).save()
    Action_Argument(name='date', description='', type='str',
                    action=set_job_log_severity).save()
    Action_Argument(name='local_severity', description='', type='int',
                    action=set_job_log_severity).save()

    # set_job_stat_policy
    set_job_stat_policy = Action(name='set_job_stat_policy')
    set_job_stat_policy.save()
    Action_Argument(name='address', description='', type='ip',
                    action=set_job_stat_policy).save()
    Action_Argument(name='job_name', description='', type='str',
                    action=set_job_stat_policy).save()
    Action_Argument(name='stat_name', description='', type='str',
                    action=set_job_stat_policy).save()
    Action_Argument(name='storage', description='', type='bool',
                    action=set_job_stat_policy).save()
    Action_Argument(name='broadcast', description='', type='bool',
                    action=set_job_stat_policy).save()
    Action_Argument(name='date', description='', type='str',
                    action=set_job_stat_policy).save()


class Migration(migrations.Migration):

    dependencies = [
        ('openbach_django', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_actions),
    ]

