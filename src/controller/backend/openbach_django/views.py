#!/usr/bin/env python

# OpenBACH is a generic testbed able to control/configure multiple
# network/physical entities (under test) and collect data from them. It is
# composed of an Auditorium (HMIs), a Controller, a Collector and multiple
# Agents (one for each network entity that wants to be tested).
#
#
# Copyright © 2016 CNES
#
#
# This file is part of the OpenBACH testbed.
#
#
# OpenBACH is a free software : you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see http://www.gnu.org/licenses/.


"""The implementation of the openbach functions"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
 * Joaquin MUGUERZA <joaquin.muguerza@toulouse.viveris.com>
'''


import os
import tempfile
import traceback
from contextlib import suppress
try:
    # Try to use a better implementation if it is installed
    import simplejson as json
except ImportError:
    import json

from django.views.generic import base
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse, HttpResponse, Http404
from django.db.utils import IntegrityError

import yaml

from .utils import send_fifo, extract_integer


class GenericView(base.View):
    """Base class for our own class-based views"""

    def _dispatch(self, request, *args, **kwargs):
        """Wraps every response from the various calls into a
        JSON response.
        """

        if request.FILES:
            request.JSON = request.POST
        else:
            try:
                data = request.body.decode()
            except Exception:
                return JsonResponse(
                        status=500,
                        data={'error': traceback.format_exc()})
            if not data:
                data = '{}'
            try:
                request.JSON = json.loads(data)
            except ValueError:
                return JsonResponse(
                        status=400,
                        data={'error': 'API error: data should be sent as JSON in the request body'})

        try:
            response = super().dispatch(request, *args, **kwargs)
        except Exception:
            return JsonResponse(
                    status=500,
                    data={'error': traceback.format_exc()})
        try:
            message, status = response
        except ValueError:
            return response
        else:
            if message is None:
                return HttpResponse(status=status)
            return JsonResponse(data=message, status=status, safe=False)

    def dispatch(self, request, *args, **kwargs):
        response = self._dispatch(request, *args, **kwargs)
        response['Access-Control-Allow-Credentials'] = True
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = self.allowed_methods
        with suppress(KeyError):
            requested_headers = request.META['HTTP_ACCESS_CONTROL_REQUEST_HEADERS']
            response['Access-Control-Allow-Headers'] = requested_headers
        return response

    @property
    def allowed_methods(self):
        return ', '.join(
                verb.upper()
                for verb in self.http_method_names
                if hasattr(self, verb)
        )

    def conductor_execute(self, **command):
        """Send a command to openbach_conductor"""
        command['_username'] = self.request.user.get_username()
        response = send_fifo(command)
        result = json.loads(response)
        returncode = result.pop('returncode')
        return result['response'], returncode

    def _debug(self):
        """Use me when creating new routes to check that everything is OK"""

        print(
            self.__class__.__name__,
            self.request.GET,
            self.request.JSON,
            self.request.body,
            self.args,
            self.kwargs)

        return {'msg': 'Route is created but no logic is associated'}, 200


class StateView(GenericView):
    state_type = None

    def get(self, request, id=None, name=None, address=None):
        """compute status of agents or jobs on it"""

        try:
            function = getattr(self, '_state_' + self.state_type)
        except AttributeError:
            return {'msg': 'POST data malformed: unknown state_type'
                    ' {}'.format(self.state_type)}, 400

        if self.state_type == 'job':
            return function(request, name)
        if self.state_type == 'job_instance':
            return function(request, id)
        if self.state_type in ('collector', 'agent'):
            return function(request, address)
        return function(request)

    def _state_collector(self, request, address):
        """Return the status of the last commands on the Collector"""
        return self.conductor_execute(
                command='state_collector',
                address=address)

    def _state_agent(self, request, address):
        """Return the status of the last commands on the Agent"""
        return self.conductor_execute(
                command='state_agent',
                address=address)

    def _state_job(self, request, name):
        """Return the status of the last commands on the Job"""
        try:
            address = request.GET['address']
        except KeyError as e:
            return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

        return self.conductor_execute(
                command='state_job',
                address=address, name=name)

    def _state_file(self, request):
        try:
            filename = request.GET['filename']
            remote_path = request.GET['path']
            address = request.GET['agent_ip']
        except KeyError as e:
            return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

        return self.conductor_execute(
                command='state_push_file', name=filename,
                path=remote_path, address=address)

    def _state_job_instance(self, request, id):
        """Return the state of the commands on the Job_Instance"""
        return self.conductor_execute(
                command='state_job_instance',
                instance_id=int(id))


class CollectorsView(GenericView):
    """Manage actions for agents without an ID"""

    def get(self, request):
        """list all collectors"""
        return self.conductor_execute(command='list_collectors')

    def post(self, request):
        """create a new collector"""
        try:
            address = request.JSON['address']
            name = request.JSON['name']
        except KeyError as e:
            return {'msg': 'Missing parameter {}'.format(e)}, 400

        return self.conductor_execute(
                command='add_collector',
                address=address, name=name,
                username=request.JSON.get('username'),
                password=request.JSON.get('password'),
                logs_port=request.JSON.get('logs_port'),
                logs_query_port=request.JSON.get('logs_query_port'),
                cluster_name=request.JSON.get('cluster_name'),
                stats_port=request.JSON.get('stats_port'),
                stats_query_port=request.JSON.get('stats_query_port'),
                database_name=request.JSON.get('database_name'),
                database_precision=request.JSON.get('database_precision'),
                broadcast_mode=request.JSON.get('broadcast_mode'),
                broadcast_port=request.JSON.get('broadcast_port'),
                skip_playbook=request.JSON.get('skip_playbook', False))


class CollectorView(GenericView):
    """Manage actions on specific agents"""

    def get(self, request, address):
        """get the informations of this collector"""
        return self.conductor_execute(
                command='infos_collector', address=address)

    def post(self, request, address):
        """change the address of this collector"""
        try:
            new_address = request.JSON['address']
        except KeyError:
            return {'msg': 'Missing parameter \'address\''}, 400

        return self.conductor_execute(
                command='change_collector_address',
                address=address, new_address=new_address)

    def delete(self, request, address):
        """remove a collector from the database"""
        return self.conductor_execute(
                command='delete_collector', address=address)

    def put(self, request, address):
        """modify a collector"""
        return self.conductor_execute(
                command='modify_collector', address=address,
                logs_port=request.JSON.get('logs_port'),
                logs_query_port=request.JSON.get('logs_query_port'),
                cluster_name=request.JSON.get('cluster_name'),
                stats_port=request.JSON.get('stats_port'),
                stats_query_port=request.JSON.get('stats_query_port'),
                database_name=request.JSON.get('database_name'),
                database_precision=request.JSON.get('database_precision'),
                broadcast_mode=request.JSON.get('broadcast_mode'),
                broadcast_port=request.JSON.get('broadcast_port'))


class BaseAgentView(GenericView):
    """Abstract base class used to factorize agent creation"""


class AgentsView(BaseAgentView):
    """Manage actions for agents without an ID"""

    def get(self, request):
        """list all agents"""
        return self.conductor_execute(
                command='list_agents',
                update='update' in request.GET)

    def post(self, request):
        """create a new agent"""
        try:
            return self.conductor_execute(
                    command='install_agent',
                    name=request.JSON['name'],
                    address=request.JSON['address'],
                    collector=request.JSON['collector_ip'],
                    username=request.JSON.get('username'),
                    password=request.JSON.get('password'),
                    skip_playbook=request.JSON.get('skip_playbook', False))
        except KeyError as e:
            return {'msg': 'Missing parameter {}'.format(e)}, 400


class AgentView(BaseAgentView):
    """Manage actions on specific agents"""

    def get(self, request, address):
        """get the informations of this agent"""
        return self.conductor_execute(
                command='infos_agent', address=address,
                update='update' in request.GET)

    def post(self, request, address):
        """dispatch the request to the correct method"""
        action = request.JSON.get('action', 'assign_collector')

        try:
            function = getattr(self, '_action_' + action)
        except AttributeError:
            return {'msg': 'POST data malformed: unknown action {}'.format(action)}, 400

        return function(request, address)

    def _action_assign_collector(self, request, address):
        """assign a collector to the agent"""
        try:
            collector_ip = request.JSON['collector_ip']
        except KeyError as e:
            return {'msg': 'Missing parameter {}'.format(e)}, 400

        return self.conductor_execute(
                command='assign_collector',
                address=address, collector=collector_ip)

    def _action_log_severity(self, request, address):
        """change the log severity on an agent"""

        try:
            severity = extract_integer(request.JSON, 'severity')
            local_severity = extract_integer(request.JSON, 'local_severity')
        except ValueError as e:
            return {'msg': 'POST data malformed: \'{}\' is not an integer'.format(e)}, 400
        if severity is None:
            return {'msg': 'POST data malformed: \'severity\' missing'}, 400

        return self.conductor_execute(
                command='set_log_severity_agent',
                address=address, severity=severity,
                local_severity=local_severity)

    def delete(self, request, address):
        """remove an agent from the database"""
        return self.conductor_execute(
                command='uninstall_agent', address=address)


class BaseJobView(GenericView):
    """Abstract base class used to factorize jobs creation"""

    def _create_job(self, job_name, compressed_sources):
        """Helper function to factorize out the job creation code"""
        with tempfile.NamedTemporaryFile('wb', delete=False) as f:
            for chunk in compressed_sources.chunks():
                f.write(chunk)
        os.chmod(f.name, 0o644)

        return self.conductor_execute(
                command='add_tar_job',
                name=job_name, path=f.name)

    def _action_install(self, names, addresses):
        """Install jobs on some agents"""
        try:
            severity = extract_integer(self.request.JSON, 'severity', default=2)
            l_severity = extract_integer(self.request.JSON, 'local_severity', default=2)
        except ValueError as e:
            return {'msg': 'POST data malformed: {} '
                    'should be an integer'.format(e)}, 400

        return self.conductor_execute(
                command='install_jobs',
                names=names, addresses=addresses,
                severity=severity, local_severity=l_severity)

    def _action_uninstall(self, names, addresses):
        """Uninstall jobs from some agents"""
        return self.conductor_execute(
                command='uninstall_jobs',
                names=names, addresses=addresses)


class JobsView(BaseJobView):
    """Manage actions for jobs without an ID"""

    def get(self, request):
        """get the list of jobs  """

        if 'external' in request.GET:
            return self.conductor_execute(command='list_external_jobs')

        try:
            string_to_search = request.GET['string_to_search']
        except KeyError:
            try:
                address = request.GET['address']
            except KeyError:
                return self._get_available_jobs()
            else:
                update = 'update' in request.GET
                return self._get_installed_jobs(address, update)
        else:
            ratio = request.GET.get('ratio')
            return self._get_available_jobs(string_to_search, ratio)

    def _get_available_jobs(self, string_to_search=None, ratio=None):
        """List all the available jobs in the bechmark or the
        ones whose keywords are matching string_to_search.
        """
        data = {'command': 'list_jobs', 'string_to_search': string_to_search}
        if ratio is not None:
            data['ratio'] = float(ratio)
        return self.conductor_execute(**data)

    def _get_installed_jobs(self, address, update):
        """list all the Jobs installed on an Agent"""
        return self.conductor_execute(
                command='list_installed_jobs',
                address=address, update=update)

    def post(self, request):
        """create a new job or install/uninstall several jobs"""
        try:
            action = request.JSON['action']
        except KeyError:
            # Create a new job
            try:
                name = request.JSON['name']
            except KeyError as e:
                return {'msg': 'POST data malformed: name missing'}, 400

            with suppress(KeyError):
                compressed_sources = request.FILES['file']
                return self._create_job(name, compressed_sources)

            with suppress(KeyError):
                path = request.JSON['path']
                return self.conductor_execute(
                        command='add_job',
                        name=name, path=path)

            return self.conductor_execute(
                    command='add_external_job',
                    name=name)
        else:
            # Execute (un)installation of several jobs
            try:
                names = request.JSON['names']
                addresses = request.JSON['addresses']
            except KeyError as e:
                return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

            try:
                function = getattr(self, '_action_' + action)
            except KeyError:
                return {'msg': 'POST data malformed: unknown action '
                        '\'{}\' for this route'.format(action)}, 400

            if not isinstance(addresses, list):
                addresses = [addresses]
            if not isinstance(names, list):
                names = [names]
            return function(names, addresses)


class JobView(BaseJobView):
    """Manage actions on specific jobs"""

    def get(self, request, name):
        """compute status of a job"""

        type_ = request.GET.get('type', 'json')
        if type_ not in {'json', 'statistics', 'help', 'keywords'}:
            return {'msg': 'Data malformed: unknown type {}'.format(type_)}, 400

        command = 'infos_job' if type_ == 'json' else 'get_{}_job'.format(type_)
        return self.conductor_execute(
                command=command, name=name)

    def delete(self, request, name):
        """remove a job from the database"""
        return self.conductor_execute(command='delete_job', name=name)

    def post(self, request, name):
        """execute various action on a job"""
        try:
            action = request.JSON['action']
            addresses = request.JSON['addresses']
        except KeyError as e:
            return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

        try:
            function = getattr(self, '_action_' + action)
        except AttributeError:
            return {'msg': 'POST data malformed: unknown action {}'.format(action)}, 400

        if not isinstance(addresses, list):
            addresses = [addresses]

        return function([name], addresses)

    def _action_log_severity(self, names, addresses):
        """change log severity of a job"""
        name, = names
        try:
            address, = addresses
        except ValueError:
            return {'msg': 'POST data malformed: \'addresses\' should '
                    'contain 1 item for action \'log_severity\''}, 400
        try:
            severity = extract_integer(self.request.JSON, 'severity')
            local_severity = extract_integer(self.request.JSON, 'local_severity')
        except ValueError as e:
            return {'msg': 'POST data malformed: \'{}\' is not an integer'.format(e)}, 400
        if severity is None:
            return {'msg': 'POST data malformed: \'severity\' missing'}, 400

        return self.conductor_execute(
                command='set_log_severity_job',
                address=address, name=name,
                severity=severity,
                local_severity=local_severity,
                date=self.request.JSON.get('date'))

    def _action_stat_policy(self, names, addresses):
        """change statistics policy of a job"""
        name, = names
        try:
            address, = addresses
        except ValueError:
            return {'msg': 'POST data malformed: \'addresses\' should '
                    'contain 1 item for action \'stat_policy\''}, 404

        return self.conductor_execute(
                command='set_statistics_policy_job',
                name=name, address=address,
                stat_name=self.request.JSON.get('stat_name'),
                storage=self.request.JSON.get('storage'),
                broadcast=self.request.JSON.get('broadcast'),
                date=self.request.JSON.get('date'))


class BaseJobInstanceView(GenericView):
    """Abstract base class used to factorize job instances management"""

    def _action_stop(self, ids):
        """stop the given job instances"""
        return self.conductor_execute(
                command='stop_job_instances', instance_ids=ids,
                date=self.request.JSON.get('date'))


class JobInstancesView(BaseJobInstanceView):
    """Manage actions on job instances without an ID"""

    def get(self, request):
        """list all job instances"""
        return self.conductor_execute(
                command='list_job_instances',
                addresses=request.GET.getlist('address'),
                update='update' in request.GET)

    def post(self, request):
        """execute various actions for job instances without an ID"""

        try:
            action = request.JSON['action']
        except KeyError:
            return {'msg': 'POST data malformed: missing action'}, 400

        try:
            function = getattr(self, '_action_' + action)
        except AttributeError:
            return {'msg': 'POST data malformed: unknown action '
                    '\'{}\' for this route'.format(action)}, 400

        return function()

    def _action_stop(self):
        """stop the job instances provided in the request body"""
        try:
            ids = self.request.JSON['job_instance_ids']
        except KeyError:
            return {'msg': 'POST data malformed: missing job_instance_ids'}, 400
        return super()._action_stop(ids)

    def _action_start(self):
        """start an instance of the given job on the given agent"""
        try:
            agent_ip = self.request.JSON['agent_ip']
            job_name = self.request.JSON['job_name']
            instance_args = self.request.JSON['instance_args']
        except KeyError as e:
            return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

        return self.conductor_execute(
                command='start_job_instance',
                name=job_name, address=agent_ip,
                arguments=instance_args,
                date=self.request.JSON.get('date'),
                interval=self.request.JSON.get('interval'))

    def _action_kill(self):
        """stop all the scenario instances and job instances"""
        return self.conductor_execute(
                command='kill_all',
                date=self.request.JSON.get('date'))


class JobInstanceView(BaseJobInstanceView):
    """Manage actions on specific job instances"""

    def get(self, request, id):
        """compute status of a job instance"""
        return self.conductor_execute(
                command='status_job_instance',
                instance_id=int(id),
                update='update' in request.GET)

    def post(self, request, id):
        """manage the life-cycle of a job instance"""

        try:
            action = request.JSON['action']
        except KeyError:
            return {'msg': 'POST data malformed: missing action'}, 400

        try:
            function = getattr(self, '_action_' + action)
        except AttributeError:
            return {'msg': 'POST data malformed: unknown action '
                    '\'{}\' for this route'.format(action)}, 400

        return function(int(id))

    def _action_stop(self, id):
        """stop the given job instance"""
        return super()._action_stop([id])

    def _action_restart(self, id):
        """restart the given job instance"""
        try:
            instance_args = self.request.JSON['instance_args']
        except KeyError as e:
            return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

        return self.conductor_execute(
                command='restart_job_instance',
                instance_id=id, arguments=instance_args,
                date=self.request.JSON.get('date'),
                interval=self.request.JSON.get('interval'))


class ScenariosView(GenericView):
    """Manage actions on scenarios without an ID"""

    def get(self, request, project_name=None):
        """list all scenarios"""
        return self.conductor_execute(
                command='list_scenarios',
                project=project_name)

    def post(self, request, project_name=None):
        """create a new scenario"""
        return self.conductor_execute(
                command='create_scenario',
                json_data=request.JSON,
                project=project_name)


class ScenarioView(GenericView):
    """Manage action on specific scenario"""

    def get(self, request, scenario_name, project_name=None):
        """get a scenario"""
        return self.conductor_execute(
                command='infos_scenario',
                name=scenario_name, project=project_name)

    def put(self, request, scenario_name, project_name=None):
        """modify a scenario"""
        return self.conductor_execute(
                command='modify_scenario', json_data=request.JSON,
                name=scenario_name, project=project_name)

    def delete(self, request, scenario_name, project_name=None):
        """remove a scenario from the database"""
        return self.conductor_execute(
                command='delete_scenario',
                name=scenario_name, project=project_name)


class ScenarioInstancesView(GenericView):
    """Manage actions on scenarios without an ID"""

    def get(self, request, scenario_name=None, project_name=None):
        """list all scenario instances"""
        return self.conductor_execute(
                command='list_scenario_instances',
                name=scenario_name, project=project_name)

    def post(self, request, scenario_name=None, project_name=None):
        """start a new scenario instance"""
        return self.conductor_execute(
                command='start_scenario_instance',
                scenario_name=scenario_name, project=project_name,
                arguments=request.JSON.get('arguments'),
                date=request.JSON.get('date'))


class ScenarioInstanceView(GenericView):
    """Manage action on specific scenario"""

    def get(self, request, id):
        """get infos of a scenario instance"""
        return self.conductor_execute(
                command='infos_scenario_instance',
                instance_id=int(id))

    def post(self, request, id):
        """stop a scenario instance"""
        return self.conductor_execute(
                command='stop_scenario_instance',
                instance_id=int(id), date=request.JSON.get('date'))

    def delete(self, request, id):
        """remove a scenario instance from the database"""
        return self.conductor_execute(
                command='remove_scenario_instance',
                instance_id=int(id))


class ProjectsView(GenericView):
    """Manage actions on projects without an ID"""

    def get(self, request):
        """list all projects"""
        return self.conductor_execute(command='list_projects')

    def post(self, request):
        """create a new project"""
        return self.conductor_execute(
                command='create_project', json_data=request.JSON,
                ignore_topology='ignore_topology' in request.GET)


class ProjectView(GenericView):
    """Manage action on specific project"""

    def get(self, request, project_name):
        """get a project"""
        return self.conductor_execute(
                command='infos_project', name=project_name)

    def put(self, request, project_name):
        """modify a project"""
        return self.conductor_execute(
                command='modify_project',
                json_data=request.JSON,
                name=project_name)

    def delete(self, request, project_name):
        """remove a project from the database"""
        return self.conductor_execute(
                command='delete_project', name=project_name)
    
    def post(self, request, project_name):
        """refresh a project's network topology"""
        if request.JSON:
            return self.conductor_execute(
                    command='modify_networks', name=project_name,
                    json_data=request.JSON.get('networks', []))
        return self.conductor_execute(
                command='refresh_topology_project', name=project_name)


class EntitiesView(GenericView):
    """Manage actions on entities for a project"""

    def get(self, request, project_name):
        """List all entities for the project"""
        return self.conductor_execute(
                command='list_entities',
                project=project_name)

    def post(self, request, project_name):
        """Create a new entity for the project"""
        return self.conductor_execute(
                command='add_entity',
                project=project_name,
                json_data=request.JSON)


class EntityView(GenericView):
    """Manage actions on specific entities for a project"""

    def get(self, request, project_name, entity_name):
        """Return informations on the requested entity"""
        return self.conductor_execute(
                command='infos_entity',
                project=project_name,
                name=entity_name)

    def put(self, request, project_name, entity_name):
        """Modify an existing entity"""
        return self.conductor_execute(
                command='modify_entity',
                project=project_name,
                name=entity_name,
                json_data=request.JSON)

    def delete(self, request, project_name, entity_name):
        """Delete an existing entity"""
        return self.conductor_execute(
                command='delete_entity',
                project=project_name,
                name=entity_name)


class LogsView(GenericView):
    """Manage actions relative to logs retrieval"""

    def get(self, request):
        """Return the list of orphaned logs"""
        try:
            level = extract_integer(request.GET, 'level', default=5)
            delay = extract_integer(request.GET, 'delay')
        except ValueError as e:
            return {'msg': 'GET data malformed: {} '
                    'should be an integer'.format(e)}, 400

        return self.conductor_execute(
                command='orphaned_logs',
                level=level, delay=delay)


class StatisticsView(GenericView):
    """Manage actions relative to statistics of a project"""

    def get(self, request, project):
        return self.conductor_execute(
                command='statistics_names',
                project=project)


class StatisticView(GenericView):
    """Manage actions relative to statistics of a job instance"""

    def get(self, request, job_instance_id):
        instance_id = int(job_instance_id)
        suffix = request.GET.get('suffix')
        try:
            statistic_name = request.GET['name']
        except KeyError:
            if 'origin' in request.GET:
                return self.conductor_execute(
                        command='statistics_origin',
                        instance_id=instance_id)
            else:
                return self.conductor_execute(
                        command='statistics_names_and_suffixes',
                        instance_id=instance_id)

        else:
            histogram = request.GET.get('histogram')
            try:
                buckets = int(histogram)
            except (ValueError, TypeError):
                if 'comparative' in request.GET:
                    return self.conductor_execute(
                            command='statistics_comparison',
                            instance_id=instance_id,
                            name=statistic_name,
                            suffix=suffix)
                else:
                    return self.conductor_execute(
                            command='statistics_values',
                            instance_id=instance_id,
                            name=statistic_name,
                            suffix=suffix)
            else:
                return self.conductor_execute(
                        command='statistics_histogram',
                        instance_id=instance_id,
                        name=statistic_name,
                        suffix=suffix,
                        buckets=buckets)


class LoginView(GenericView):
    """Manage actions relative to user authentication"""

    @staticmethod
    def _user_to_json(user):
        """Helper method to convert a user to its JSON response"""
        return {
                'username': user.get_username(),
                'name': user.get_full_name(),
                'first_name': user.first_name,
                'last_name': user.last_name,
                'is_user': user.is_active,
                'is_admin': user.is_staff,
                'email': user.email,
        }

    def get(self, request):
        """Return profile of connected user, or None if anonymous user"""
        user = request.user
        if not user.is_authenticated():
            return {
                    'username': None,
                    'name': None,
                    'first_name': None,
                    'last_name': None,
                    'is_user': False,
                    'is_admin': False,
                    'email': None,
            }, 200

        return self._user_to_json(user), 200

    def post(self, request):
        """Create new or authenticate user"""
        action = request.JSON.get('action', 'authenticate')
        try:
            action_handler = getattr(self, '_do_' + action)
        except AttributeError:
            return {'msg': 'Unknown login action \'{}\''.format(action)}, 400

        try:
            username = request.JSON['login']
            password = request.JSON['password']
        except KeyError as e:
            return {'msg': 'Missing login field \'{}\''.format(e)}, 400
        return action_handler(request, username, password)

    def _do_create(self, request, username, password):
        """Handle creation of a new user"""
        email = request.JSON.get('email')
        try:
            user = User.objects.create_user(username, email, password)
        except IntegrityError:
            return {'msg': 'Cannot create a new user \'{}\': '
                    'the username already exists'.format(username)}, 409
        user.is_active = False
        user.is_staff = False
        user.first_name = request.JSON.get('first_name', '')
        user.last_name = request.JSON.get('last_name', '')
        user.save()
        return None, 204

    def _do_authenticate(self, request, username, password):
        """Handle authentication of the current user"""
        if request.user.is_authenticated():
            return {'msg': 'A user is already connected. Please '
                    'logout first and then log back in.'}, 409

        user = authenticate(username=username, password=password)
        if user is None:
            return {'msg': 'Wrong Credentials'}, 401
        login(request, user)
        return self._user_to_json(user), 200

    def put(self, request):
        """Modify profile of connected user"""
        user = request.user
        if not user.is_authenticated():
            return {'msg': 'User is disconnected, cannot modify profile'}, 403

        try:
            username = request.JSON['login']
        except KeyError as e:
            return {'msg': 'Missing profile field \'{}\''.format(e)}, 400

        password = request.JSON.get('password')

        if user.get_username() != username:
            return {'msg': 'Error: the provided username and the '
                    'username of the current user does not match'}, 400

        user.email = request.JSON.get('email', '')
        user.first_name = request.JSON.get('first_name', '')
        user.last_name = request.JSON.get('last_name', '')
        if password is not None:
            user.set_password(password)
        user.save()

        if password is not None:
            user = authenticate(username=username, password=password)
            login(request, user)

        return self._user_to_json(user), 200

    def delete(self, request):
        """Disconnect connected user"""
        logout(request)
        return None, 204


class UsersView(GenericView):
    """Manage actions relative to user in a generic sense"""

    def get(self, request):
        """Return the list of registered users"""
        return self.conductor_execute(command='list_users')

    def put(self, request):
        """Modify permissions of users"""
        permissions = request.JSON.get('permissions', [])
        return self.conductor_execute(
                command='update_users',
                users_permissions=permissions)

    def delete(self, request):
        """Delete users"""
        users = request.JSON.get('usernames', [])
        return self.conductor_execute(command='delete_users', usernames=users)


class VersionView(GenericView):
    """Manage actions relative to the current version of OpenBACH"""

    def get(self, request):
        """Return the current version"""
        try:
            with open('/opt/openbach/controller/version') as version_file:
                openbach_infos = yaml.load(version_file)
        except OSError as e:
            return {'msg': 'Cannot fetch version: {}'.format(e)}, 500
        return {'openbach_version': openbach_infos['version']}, 200


def push_file(request):
    do_remove = True

    try:
        remote_path = request.POST['path']
        address = request.POST['agent_ip']
    except KeyError as e:
        return JsonResponse(
                status=400,
                data={'msg': 'POST data malformed: {} missing'.format(e)})

    try:
        uploaded_file = request.FILES['file']
    except KeyError:
        try:
            path = request.POST['local_path']
        except KeyError:
            return JsonResponse(
                    status=400,
                    data={
                        'msg': 'POST data malformed: neither '
                        '\'local_path\' nor a file was sent',
                    })
        else:
            do_remove = False
    else:
        # Copy file to disk
        path = '/tmp/{}'.format(uploaded_file.name)
        with open(path, 'wb') as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)

    try:
        # Mock using a class-based view to contact the conductor
        view = GenericView()
        view.request = request
        return view.conductor_execute(
                command='push_file', address=address,
                local_path=path, remote_path=remote_path)
    finally:
        os.remove(path)


def download_csv(request, id):
    path = None
    # Mock using a class-based view to contact the conductor
    view = GenericView()
    view.request = request
    path, _ = view.conductor_execute(
            command='export_scenario_instance', 
            instance_id=int(id))
    try:
        with open(path) as f:
            response = HttpResponse(f.read(), content_type='application/force_download')
            response['Content-Disposition'] = 'attachment; filename="scenario{}.csv"'.format(id)
    except TypeError as e:
        raise Http404
    except OSError as e:
        os.remove(path)
        raise
    else:
        os.remove(path)
        return response
