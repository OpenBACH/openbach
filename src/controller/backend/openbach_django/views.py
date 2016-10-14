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
   
   
   
   @file     views.py
   @brief    The implementation of the openbach-function
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


try:
    # Try to use a better implementation if it is installed
    import simplejson as json
except ImportError:
    import json
import socket
import os

from django.views.generic import base
from django.http import JsonResponse

class GenericView(base.View):
    """Base class for our own class-based views"""

    def dispatch(self, request, *args, **kwargs):
        """Wraps every response from the various calls into a
        JSON response.
        """

        if request.POST:
            return JsonResponse(
                status=405,
                data={'error': 'Methode not allowed, use JSON instead'})

        data = request.body.decode()
        if data:
            try:
                request.JSON = json.loads(data)
            except ValueError:
                return JsonResponse(
                        status=400,
                        data={'msg': 'API error: data should be sent as JSON in the request body'})
        else:
            request.JSON = {}

        response = super().dispatch(request, *args, **kwargs)
        try:
            message, status = response
        except ValueError:
            return JsonResponse(
                    status=500,
                    data={'msg': 'Programming error: method does not return expected value'})
        else:
            return JsonResponse(data=message, status=status)


    @staticmethod
    def conductor_execute(command):
        """Send a command to openbach-conductor"""

        conductor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conductor.connect(('localhost', 1113))
        conductor.send(json.dumps(command).encode())
        recv = conductor.recv(9999)
        result = json.loads(recv.decode())
        returncode = result.pop('returncode')
        conductor.close()
        return result, returncode


    def _install_jobs(self, addresses, names, severity=4, local_severity=4):
        """Helper function used to create an agent or a job"""

        data = { 'addresses': addresses, 'names': names, 'severity': severity,
                 'local_severity': local_severity, 'command': 'install_jobs' }

        return self.conductor_execute(data)


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


class StatusView(GenericView):
    status_type = None

    def get(self, request, id=None, name=None):
        """compute status of agents or jobs on it"""

        try:
            function = getattr(self, '_status_' + self.status_type)
        except AttributeError:
            return {'msg': 'POST data malformed: unknown status_type'
                    ' {}'.format(self.status_type)}, 400

        if self.status_type == 'job':
            return function(request, name)
        if self.status_type == 'job_instance':
            return function(request, id)
        return function(request)


    def _status_agents(self, request):
        try:
            action = request.GET['action']
            address = request.GET['address']
        except KeyError as e:
            return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

        try:
            function = getattr(self, '_action_' + action)
        except AttributeError:
            return {'msg': 'POST data malformed: unknown action'
                    ' {}'.format(action)}, 400

        return function(address)


    def _status_jobs(self, request):
        try:
            action = request.GET['action']
            if action != 'status_retrieve_status':
                name = request.GET['name']
            address = request.GET['address']
        except KeyError as e:
            return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

        try:
            function = getattr(self, '_action_' + action)
        except AttributeError:
            return {'msg': 'POST data malformed: unknown action'
                    ' {}'.format(action)}, 400

        if action == 'status_retrieve_status':
            return function(address)
        return function(address, name)


    def _status_job(self, request, name):
        try:
            action = request.GET['action']
            address = request.GET['address']
        except KeyError as e:
            return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

        try:
            function = getattr(self, '_action_' + action)
        except AttributeError:
            return {'msg': 'POST data malformed: unknown action'
                    ' {}'.format(action)}, 400

        return function(address, name)


    def _status_file(self, request):
        try:
            filename = request.GET['filename']
            remote_path = request.GET['path']
            address = request.GET['agent_ip']
        except KeyError as e:
            return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

        data = { 'address': address, 'command': 'status_push_file',
                 'remote_path': remoth_path, 'filename': filename }

        return self.conductor_execute(data)


    def _status_job_instances(self, request):
        try:
            action = request.GET['action']
            job_instance_id = request.GET['job_instance_id']
        except KeyError as e:
            return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

        try:
            function = getattr(self, '_action_' + action)
        except AttributeError:
            return {'msg': 'POST data malformed: unknown action'
                    ' {}'.format(action)}, 400

        return function(job_instance_id)


    def _status_job_instance(self, request, id):
        try:
            action = request.GET['action']
        except KeyError as e:
            return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

        try:
            function = getattr(self, '_action_' + action)
        except AttributeError:
            return {'msg': 'POST data malformed: unknown action'
                    ' {}'.format(action)}, 400

        return function(id)


    def _action_install(self, address):
        """Return the status of the installation of the Agent"""
        data = { 'address': address, 'command': 'status_install_agent' }

        return self.conductor_execute(data)


    def _action_uninstall(self, address):
        """Return the status of the uninstallation of the Agent"""
        data = { 'address': address, 'command': 'status_uninstall_agent' }

        return self.conductor_execute(data)


    def _action_retrieve_status(self, address):
        """Return the status of the retrievement of the status of the Agent"""
        data = { 'address': address, 'command':
                 'status_retrieve_status_agent' }

        return self.conductor_execute(data)


    def _action_status_install(self, address, name):
        """Return the status of the installation of a Job on an Agent"""
        data = { 'address': address, 'name': name,  'command':
                 'status_install_jobs' }

        return self.conductor_execute(data)


    def _action_status_uninstall(self, address, name):
        """Return the status of the uninstallation of a Job on an Agent"""
        data = { 'address': address, 'name': name,  'command':
                 'status_uninstall_jobs' }

        return self.conductor_execute(data)


    def _action_status_retrieve_status(self, address):
        """Return the status of the retrievement of the list of installed Jobs"""
        data = { 'address': address, 'command':
                 'status_retrieve_status_jobs' }

        return self.conductor_execute(data)


    def _action_log_severity(self, address, name):
        """Return the status of the setting of a now log severity"""
        data = { 'address': address, 'name': name, 'command':
                 'status_set_job_log_severity' }

        return self.conductor_execute(data)


    def _action_stat_policy(self, address, name):
        """Return the status of the setting of a now stats policy"""
        data = { 'address': address, 'name': name, 'command':
                 'status_set_job_stat_policy' }

        return self.conductor_execute(data)


    def _action_start(self, job_instance_id):
        """Return the status of the starting of a Job Instance"""
        data = { 'job_instance_id': job_instance_id, 'command':
                 'status_start_job_instance' }

        return self.conductor_execute(data)


    def _action_stop(self, job_instance_id):
        """Return the status of the stopping of one or more job instance"""
        data = {'job_instance_id': job_instance_id, 'command':
                'status_stop_job_instance'}

        return self.conductor_execute(data)


    def _action_restart(self, id):
        """Return the status of the restarting of a Job Instance"""
        data = { 'job_instance_id': id, 'command':
                 'status_restart_job_instance' }

        return self.conductor_execute(data)


    def _action_watch(self, id):
        """Return the status of the starting of a watch"""
        data = { 'job_instance_id': id, 'command':
                 'status_watch_job_instance' }

        return self.conductor_execute(data)


class BaseAgentView(GenericView):
    """Abstract base class used to factorize agent creation"""

    def _create_agent(self, address, username, collector, name, password):
        """Helper function to factorize out the agent creation code"""

        data = { 'address': address, 'collector': collector, 'username':
                username, 'password': password, 'name': name, 'command':
                'install_agent' }

        return self.conductor_execute(data)


    def _action_retrieve_status(self, addresses, update):
        """Retrieve the status of an Agent"""

        data = { 'addresses': addresses, 'command': 'retrieve_status_agents' }
        if update:
            data['update'] = update

        return self.conductor_execute(data)


class AgentsView(BaseAgentView):
    """Manage actions for agents without an ID"""

    def get(self, request):
        """list all agents"""

        update = 'update' in request.GET
        data = { 'command': 'list_agents', 'update': update }

        return self.conductor_execute(data)


    def post(self, request):
        """create a new agent"""

        try:
            action = request.JSON['action']
        except KeyError:
            # Create a new Agent
            required_parameters = ('address', 'username', 'collector', 'name', 'password')
            try:
                parameters = {k: request.JSON[k] for k in required_parameters}
            except KeyError as e:
                return {'msg': 'Missing parameter {}'.format(e)}, 400

            return self._create_agent(**parameters)
        else:
            update = 'update' in request.JSON
            try:
                function = getattr(self, '_action_' + action)
            except KeyError:
                return {'msg': 'POST data malformed: unknown action '
                        '\'{}\' for this route'.format(action)}, 400
            try:
                addresses = request.JSON['addresses']
            except KeyError as e:
                return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

            return function(addresses, update)


class AgentView(BaseAgentView):
    """Manage actions on specific agents"""

    def delete(self, request, address):
        """remove an agent from the database"""

        data = { 'command': 'uninstall_agent', 'address': address }

        return self.conductor_execute(data)


class BaseJobView(GenericView):
    """Abstract base class used to factorize jobs creation"""

    def _create_job(self, job_name, job_path):
        """Helper function to factorize out the job creation code"""

        data = { 'command': 'add_job', 'name': job_name, 'path': job_path }

        return self.conductor_execute(data)


    def _action_install(self, names, addresses):
        """Install jobs on some agents"""

        severity = self.request.JSON.get('severity', 4)
        local_severity = self.request.JSON.get('local_severity', 4)

        return self._install_jobs(addresses, names, severity, local_severity)


    def _action_uninstall(self, names, addresses):
        """Uninstall jobs from some agents"""

        data = { 'command': 'uninstall_jobs', 'names': names, 'addresses':
                 addresses }

        return self.conductor_execute(data)


    def _action_retrieve_status(self, addresses):
        """Retrieve the list of installed jobs on an Agent (or multiple Agents)"""

        data = { 'addresses': addresses, 'command': 'retrieve_status_jobs' }

        return self.conductor_execute(data)


class JobsView(BaseJobView):
    """Manage actions for jobs without an ID"""

    def get(self, request):
        """list all jobs"""

        try:
            verbosity = int(request.GET.get('verbosity', 0))
        except ValueError:
            return {'msg': 'Query string malformed: \'verbosity\' should be an'
                    ' int' }, 400
        try:
            address = request.GET['address']
        except KeyError:
            return self._get_all_jobs(verbosity)
        else:
            update = 'update' in request.GET
            return self._get_installed_jobs(address, verbosity, update)


    def _get_all_jobs(self, verbosity):
        """list all the Jobs available on the benchmark"""

        data = { 'command': 'list_jobs', 'verbosity': verbosity }

        return self.conductor_execute(data)


    def _get_installed_jobs(self, address, verbosity, update):
        """list all the Jobs installed on an Agent"""

        data = { 'command': 'list_installed_jobs', 'address': address,
                 'verbosity': verbosity, 'update': update }

        return self.conductor_execute(data)


    def post(self, request):
        """create a new job or install/uninstall several jobs"""

        try:
            action = request.JSON['action']
        except KeyError:
            # Create a new job
            try:
                name = request.JSON['name']
                path = request.JSON['path']
            except KeyError as e:
                return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

            return self._create_job(name, path)
        else:
            # Execute (un)installation of several jobs
            try:
                if action != 'retrieve_status':
                    names = request.JSON['names']
                addresses = request.JSON['addresses']
            except KeyError as e:
                return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

            try:
                function = getattr(self, '_action_' + action)
            except KeyError:
                return {'msg': 'POST data malformed: unknown action '
                        '\'{}\' for this route'.format(action)}, 400

            if action != 'retrieve_status':
                if not isinstance(names, list):
                    names = [names]
            if not isinstance(addresses, list):
                addresses = [addresses]

            if action == 'retrieve_status':
                return function(addresses)
            return function(names, addresses)


class JobView(BaseJobView):
    """Manage actions on specific jobs"""

    def get(self, request, name):
        """compute status of a job"""

        type_ = request.GET.get('type', 'stats')
        try:
            function = getattr(self, '_status_' + type_)
        except AttributeError:
            return {'msg': 'Data malformed: unknown type {}'.format(type_)}, 400

        return function(name)

    def _status_help(self, name):
        """compute help status for the given job"""

        data = { 'command': 'get_job_help', 'name': name }

        return self.conductor_execute(data)


    def _status_stats(self, name):
        """compute statistics status for the given job"""

        try:
            verbosity = int(self.request.GET.get('verbosity', 0))
        except ValueError:
            return {'msg': 'Query string malformed: \'verbosity\' should be an'
                    ' int' }, 400

        data = { 'command': 'get_job_stats', 'name': name, 'verbosity':
                 verbosity }

        return self.conductor_execute(data)


    def delete(self, request, name):
        """remove a job from the database"""

        data = { 'command': 'del_job', 'name': name }

        return self.conductor_execute(data)


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
            severity = self.request.JSON['severity']
        except KeyError:
            return {'msg': 'POST data malformed: \'severity\' missing'}, 400

        data = { 'command': 'set_job_log_severity', 'address': address,
                 'job_name': name, 'severity': severity }

        local_severity = self.request.JSON.get('local_severity', None)
        if local_severity:
            data['local_severity'] = local_severity
        date = self.request.JSON.get('date', None)
        if date:
            data['date'] = date

        return self.conductor_execute(data)


    def _action_stat_policy(self, names, addresses):
        """change statistics policy of a job"""

        name, = names
        try:
            address, = addresses
        except ValueError:
            return {'msg': 'POST data malformed: \'addresses\' should '
                    'contain 1 item for action \'stat_policy\''}, 404

        data = { 'command': 'set_job_stat_policy', 'address': address,
                 'job_name': name }

        request_data = self.request.JSON
        if 'stat_name' in request_data:
            data['stat_name'] = request_data['stat_name']
        if 'storage' in request_data:
            data['storage'] = request_data['storage']
        if 'broadcast' in request_data:
            data['broadcast'] = request_data['broadcast']
        if 'date' in request_data:
            data['date'] = request_data['date']

        return self.conductor_execute(data)


class BaseJobInstanceView(GenericView):
    """Abstract base class used to factorize job instances management"""

    def _action_stop(self, ids):
        """stop the given job instances"""

        data = { 'job_instance_ids': ids, 'command': 'stop_job_instance' }
        request_data = self.request.JSON
        if 'date' in request_data:
            data['date'] = request_data['date']

        return self.conductor_execute(data)


    def _job_instance_status(self, job_instance_id, data):
        """query the status of the given installed job"""

        data['job_instance_id'] = job_instance_id
        data['command'] = 'watch_job_instance'
        del data['action']

        return self.conductor_execute(data)


class JobInstancesView(BaseJobInstanceView):
    """Manage actions on job instances without an ID"""

    def get(self, request):
        """list all job instances"""

        try:
            verbosity = int(request.GET.get('verbosity', 0))
        except ValueError:
            return {'msg': 'Query string malformed: \'verbosity\' should be an'
                    ' int' }, 400
        update = 'update' in request.GET

        data = { 'addresses': request.GET.getlist('address'), 'update':
                 update, 'verbosity': verbosity, 'command': 'list_job_instances'
               }

        return self.conductor_execute(data)


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

        if action == 'stop':
            try:
                ids = request.JSON['job_instance_ids']
            except KeyError:
                return {'msg': 'POST data malformed: missing job_instance_ids'}, 400
            return function(ids)

        return function()


    def _action_start(self):
        """start an instance of the given job on the given agent"""

        try:
            agent_ip = self.request.JSON['agent_ip']
            job_name = self.request.JSON['job_name']
            instance_args = self.request.JSON['instance_args']
        except KeyError as e:
            return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

        data = { 'command': 'start_job_instance', 'agent_ip': agent_ip,
                 'job_name': job_name, 'instance_args': instance_args  }

        request_data = self.request.JSON
        if 'date' in request_data:
            data['date'] = request_data['date']
        if 'interval' in request_data:
            data['interval'] = request_data['interval']

        return self.conductor_execute(data)


    def _action_kill(self):
        """stop all the scenario instances, job instances and watchs"""

        data = { 'command': 'kill_all' }

        request_data = self.request.JSON
        if 'date' in request_data:
            data['date'] = request_data['date']

        return self.conductor_execute(data)


class JobInstanceView(BaseJobInstanceView):
    """Manage actions on specific job instances"""

    def get(self, request, id):
        """compute status of a job instance"""

        try:
            verbosity = int(request.GET.get('verbosity', 0))
        except ValueError:
            return {'msg': 'Query string malformed: \'verbosity\' should be an'
                    ' int' }, 400
        update = 'update' in request.GET

        data = { 'command': 'status_job_instance', 'job_instance_id': id,
                 'verbosity': verbosity, 'update': update }

        return self.conductor_execute(data)


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

        if action == 'stop':
            return function([id])
        return function(id)


    def _action_restart(self, id):
        """restart the given job instance"""

        request_data = self.request.JSON
        try:
            instance_args = request_data['instance_args']
        except KeyError as e:
            return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

        data = { 'command': 'restart_job_instance', 'job_instance_id': id,
                 'instance_args': instance_args }

        if 'date' in request_data:
            data['date'] = request_data['date']
        if 'interval' in request_data:
            data['interval'] = request_data['interval']

        return self.conductor_execute(data)


    def _action_watch(self, id):
        """start a status watch for the given job instance"""

        return self._job_instance_status(id, self.request.JSON)


class ScenariosView(GenericView):
    """Manage actions on scenarios without an ID"""

    def get(self, request):
        """list all scenarios"""

        try:
            verbosity = int(request.GET.get('verbosity', 0))
        except ValueError:
            return {'msg': 'Query string malformed: \'verbosity\' should be an'
                    ' int' }, 400

        data = { 'command': 'list_scenarios', 'verbosity': verbosity }

        return self.conductor_execute(data)


    def post(self, request):
        """create a new scenario"""

        data = {
            'command': 'create_scenario',
            'scenario_json': request.JSON,
        }

        return self.conductor_execute(data)


class ScenarioView(GenericView):
    """Manage action on specific scenario"""

    def get(self, request, name):
        """get a scenario"""

        data = { 'command': 'get_scenario', 'scenario_name': name }

        return self.conductor_execute(data)


    def put(self, request, name):
        """modify a scenario"""

        data = {
            'command': 'modify_scenario',
            'scenario_json': request.JSON,
            'scenario_name': name,
        }

        return self.conductor_execute(data)


    def delete(self, request, name):
        """remove a scenario from the database"""

        data = { 'command': 'del_scenario', 'scenario_name': name }

        return self.conductor_execute(data)


class ScenarioInstancesView(GenericView):
    """Manage actions on scenarios without an ID"""

    def get(self, request):
        """list all scenario instances"""

        try:
            verbosity = int(request.GET.get('verbosity', 0))
        except ValueError:
            return {'msg': 'Query string malformed: \'verbosity\' should be an'
                    ' int' }, 400
        scenario_names = request.GET.getlist('scenario_name')
        data = { 'command': 'list_scenario_instances', 'scenario_names':
                 scenario_names, 'verbosity': verbosity }

        return self.conductor_execute(data)


    def post(self, request):
        """start a new scenario instance"""

        data = request.JSON
        data['command'] = 'start_scenario_instance'

        return self.conductor_execute(data)


class ScenarioInstanceView(GenericView):
    """Manage action on specific scenario"""

    def get(self, request, id):
        """compute status of a scenario instance"""

        try:
            verbosity = int(request.GET.get('verbosity', 0))
        except ValueError:
            return {'msg': 'Query string malformed: \'verbosity\' should be an'
                    ' int' }, 400
        data = { 'command': 'status_scenario_instance', 'scenario_instance_id':
                 id, 'verbosity': verbosity }

        return self.conductor_execute(data)


    def post(self, request, id):
        """stop a scenario instance"""

        data = { 'command': 'stop_scenario_instance', 'scenario_instance_id': id }
        date = self.request.JSON.get('date', None)
        if date:
            data['date'] = date

        return self.conductor_execute(data)


def push_file(request):
    try:
        uploaded_file = request.FILES['file']
        remote_path = request.POST['path']
        address = request.POST['agent_ip']
    except KeyError as e:
        return JsonResponse(
                status=400,
                data={'msg': 'POST data malformed: {} missing'.format(e)})

    # Copy file to disk
    path = '/tmp/{}'.format(uploaded_file.name)
    with open(path, 'wb') as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)

    data = { 'command': 'push_file', 'local_path': path, 'remote_path':
             remote_path, 'agent_ip': address }

    result = GenericView.conductor_execute(data)
    os.remove(path)

    return result

