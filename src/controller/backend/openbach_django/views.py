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


import os.path
import socket
import yaml
from operator import attrgetter
from datetime import datetime
try:
    # Try to use a better implementation if it is installed
    import simplejson as json
except ImportError:
    import json

from django.utils import timezone
from django.http import JsonResponse
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.views.generic import base

from .models import Agent, Job, Installed_Job, Job_Instance, Watch, Job_Keyword
from .models import Statistic, Required_Job_Argument, Optional_Job_Argument
from .models import Required_Job_Argument_Instance, Optional_Job_Argument_Instance
from .models import Job_Argument_Value, Statistic_Instance


class GenericView(base.View):
    """Base class for our own class-based views"""

    def dispatch(self, request, *args, **kwargs):
        """Wraps every response from the various calls into a
        JSON response.
        """
        data = request.body.decode()
        if request.POST:
            request.JSON = request.POST
        elif data:
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
    def _conductor_execute(command):
        """Send a command to openbach-conductor"""

        conductor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conductor.connect(('localhost', 1113))
        conductor.send(command.encode())
        result = conductor.recv(1024).decode()
        conductor.close()
        return result

    def _install_jobs(self, addresses, names, severity=4, local_severity=4):
        """Helper function used to create an agent or a job"""

        agents = Agent.objects.filter(pk__in=addresses)
        no_agent = set(addresses) - set(map(attrgetter('address'), agents))

        jobs = Job.objects.filter(pk__in=names)
        no_job = set(names) - set(map(attrgetter('name'), jobs))

        success = True
        for agent in agents:
            for job in jobs:
                result = self._conductor_execute('install_job {} "{}"'.format(agent.address, job.name))
                if result == 'OK':
                    installed_job = Installed_Job(
                            agent=agent, job=job,
                            severity=severity,
                            local_severity=local_severity)
                    installed_job.set_name()
                    installed_job.update_status = timezone.now()
                    installed_job.save()
                else:
                    success = False

        result = {'msg': 'OK' if success else 'At least one of the installations have failed'}
        if no_job:
            result['warning'] = 'At least one of the jobs is unknown to the controller'
            result['unknown Jobs'] = list(no_job)
        if no_agent:
            result['warning'] = ('At least one of the jobs and one of the '
                                 'agents is unknown to the controller' if
                                 'warning' in result else 'At least one of '
                                 'the agents is unknown to the controller')
            result['unknown Agents'] = list(no_agent)
        return result

    def _job_instance_launcher(self, instance, instance_args, restart=False, launch=True):
        """Helper function used to fill attributes of a job
        instance and run it on its agent
        """

        data = self.request.JSON
        instance.status = "starting ..."
        instance.update_status = timezone.now()

        if 'interval' in data:
            interval = data['interval']
            instance.start_date = timezone.now()
            instance.periodic = True
            instance.save()
            cmd = 'start_job_instance interval {} {}'.format(interval, instance.id)
        else:
            date = data.get('date', 'now')
            if date == 'now':
                instance.start_date = timezone.now()
            else:
                start_date = datetime.fromtimestamp(
                        date / 1000,
                        tz=timezone.get_current_timezone())
                instance.start_date = start_date
            instance.periodic = False
            instance.save()
            cmd = 'start_job_instance date {} {}'.format(date, instance.id)

        if restart:
            cmd = 're{}'.format(cmd)
            instance.required_job_argument_instance_set.all().delete()
            instance.optional_job_argument_instance_set.all().delete()

        for arg_name, arg_values in instance_args.items():
            try:
                argument_instance = Required_Job_Argument_Instance(
                    argument=instance.job.job.required_job_argument_set.filter(name=arg_name)[0],
                    job_instance=instance
                )
                argument_instance.save()
            except IndexError:
                try:
                    argument_instance = Optional_Job_Argument_Instance(
                        argument=instance.job.job.optional_job_argument_set.filter(name=arg_name)[0],
                        job_instance=instance
                    )
                    argument_instance.save()
                except IndexError:
                    return {'msg': 'Argument \'{}\' don\'t match with argu'
                            'ments needed or optional'.format(arg_name)}, 400
            for arg_value in arg_values:
                Job_Argument_Value(
                    value=arg_value,
                    argument_instance=argument_instance
                ).save()

        try:
            instance.check_args()
        except ValueError as e:
            return {
                'msg': 'Arguments given don\'t match with arguments needed',
                'error': e.args[0],
            }, 400

        if launch:
            result = self._conductor_execute(cmd)
            response = {'msg': result}
            if result == 'OK':
                instance.status = "Started"
                instance.update_status = timezone.now()
                instance.save()
                if not restart:
                    response['instance_id'] = instance.id
                return response, 200
            else:
                instance.delete()
                return response, 404
        else:
            return date

    def _debug(self):
        """Use me when creating new routes to check that everything is OK"""

        print(
            self.__class__.__name__,
            self.request.GET,
            self.request.POST,
            self.request.body,
            self.args,
            self.kwargs)

        return {'msg': 'Route is created but no logic is associated'}, 200


class StatusView(GenericView):
    status_type = None

    def get(self, request):
        """compute status of agents or jobs on it"""

        assert self.status_type is not None

        addresses = request.GET.getlist('address')
        addresses.insert(0, self.status_type)

        result = self._conductor_execute(' '.join(addresses))
        if result == 'OK':
            return {'msg': result}, 200
        return {
            'msg': 'At least one of the Agents isn\'t in the database',
            'addresses': result,
        }, 404


class BaseAgentView(GenericView):
    """Abstract base class used to factorize agent creation"""

    list_default_jobs = '/opt/openbach-controller/install_agent/list_default_jobs.txt'

    def _create_agent(self, address, username, collector, name, password):
        """Helper function to factorize out the agent creation code"""

        agent = Agent(address=address, username=username, collector=collector, name=name)
        agent.set_password(password)
        agent.reachable = True
        agent.update_reachable = timezone.now()
        agent.status = 'Installing ...'
        agent.update_status = timezone.now()
        try:
            agent.save()
        except IntegrityError:
            return {'msg': 'Name of the Agent already used'}, 409

        result = self._conductor_execute('install_agent {}'.format(agent.address))
        response = {'msg': result}
        if result.startswith('KO'):
            agent.delete()
            return response, 500
        agent.status = 'Available'
        agent.update_status = timezone.now()
        agent.save()
        # Recuperer la liste des jobs a installer
        with open(self.list_default_jobs) as f:
            list_jobs = [line.rstrip('\n') for line in f]
        # Installer les jobs
        result = self._install_jobs([agent.address], list_jobs)
        if result['msg'] != 'OK':
            response['warning'] = 'At least one of the default Jobs installation have failed'
        elif 'warning' in result:
            response['warning'] = result['warning']
            response['unknown Jobs'] = result['unknown Jobs']

        return response, 200


class AgentsView(BaseAgentView):
    """Manage actions for agents without an ID"""

    def get(self, request):
        """list all agents"""

        agents = Agent.objects.all()
        update = request.GET.get('update', False)
        response = {}
        if update:
            for agent in agents:
                if agent.reachable and agent.update_status < agent.update_reachable:
                    result = self._conductor_execute('update_agent {}'.format(agent.address))
                    if result.startswith('KO'):
                        response.setdefault('errors', []).append({
                            'agent_ip': agent.address,
                            'error': result[3:],
                        })
                # Moved it here to avoid extra checks in the next loop
                # Don't really know if it is OK
                agent.refresh_from_db()

        response['agents'] = [{
            'address': agent.address,
            'status': agent.status,
            'update_status': agent.update_status.astimezone(timezone.get_current_timezone()),
            'name': agent.name,
        } for agent in agents]

        return response, 200

    def post(self, request):
        """create a new agent"""

        required_parameters = ('address', 'username', 'collector', 'name', 'password')
        try:
            parameters = {k: request.JSON[k] for k in required_parameters}
        except KeyError as e:
            return {'msg': 'Missing parameter {}'.format(e)}, 400

        return self._create_agent(**parameters)


class AgentView(BaseAgentView):
    """Manage actions on specific agents"""

    def get(self, request, address):
        """compute status of an agent"""

        result = self._conductor_execute('status_agents {}'.format(address))
        if result == 'OK':
            return {'msg': result}, 200
        return {
            'msg': 'At least one of the Agents isn\'t in the database',
            'addresses': result,
        }, 404

    def put(self, request, address):
        """create a new agent"""

        required_parameters = ('username', 'collector', 'name', 'password')
        try:
            parameters = {k: request.JSON[k] for k in required_parameters}
        except KeyError as e:
            return {'msg': 'Missing parameter {}'.format(e)}, 400

        return self._create_agent(address, **parameters)

    def delete(self, request, address):
        """remove an agent from the database"""

        try:
            agent = Agent.objects.get(pk=address)
        except ObjectDoesNotExist:
            return {
                'msg': 'This Agent isn\'t in the database',
                'address': address,
            }, 404

        result = self._conductor_execute('uninstall_agent {}'.format(address))
        response = {'msg': result}
        if result == 'OK':
            agent.delete()
            return response, 200
        return response, 500


class BaseJobView(GenericView):
    """Abstract base class used to factorize jobs creation"""

    def _create_job(self, job_name, job_path):
        """Helper function to factorize out the job creation code"""

        config_prefix = os.path.join(job_path, 'files', job_name)
        config_file = '{}.yml'.format(config_prefix)
        try:
            with open(config_file, 'r') as stream:
                try:
                    content = yaml.load(stream)
                except yaml.YAMLError:
                    return {'msg': 'KO, the configuration file of the Job is not well '
                            'formed', 'configuration file': config_file}, 404
        except FileNotFoundError:
            return {'msg': 'KO, the configuration file is not present',
                    'configuration file': config_file}, 404
        try:
            job_version = content['general']['job_version']
            keywords = content['general']['keywords']
            statistics = content['statistics']
            description = content['general']['description']
            required_args = []
            args = content['arguments']['required']
            if type(args) == list:
                for arg in args:
                    required_args.append(arg)
            optional_args = []
            if content['arguments']['optional'] is not None:
                for arg in content['arguments']['optional']:
                    optional_args.append(arg)
        except KeyError:
            return {'msg': 'KO, the configuration file of the Job is not well '
                    'formed', 'configuration file': config_file}, 404
        try:
            with open('{}.help'.format(config_prefix)) as f:
                help = f.read()
        except OSError:
            help = ''

        deleted = False
        try:
            job = Job.objects.get(pk=job_name)
            job.delete()
            deleted = True
        except ObjectDoesNotExist:
            pass

        job = Job(
            name=job_name,
            path=job_path,
            help=help,
            job_version=job_version,
            description=description
        )
        job.save()

        for keyword in keywords:
            job_keyword = Job_Keyword(
                name=keyword
            )
            job_keyword.save()
            job.keywords.add(job_keyword)

        if isinstance(statistics, list):
            try:
                for statistic in statistics:
                    Statistic(
                        name=statistic['name'],
                        job=job,
                        description=statistic['description'],
                        frequency=statistic['frequency']
                    ).save()
            except IntegrityError:
                job.delete()
                if deleted:
                    return {'msg': 'KO, the configuration file of the Job is not well '
                            'formed', 'configuration file': config_file, 'warning':
                            'Old Job has been deleted'}, 409
                else:
                    return {'msg': 'KO, the configuration file of the Job is not well '
                            'formed', 'configuration file': config_file}, 409
        elif statistics is None:
            pass
        else:
            job.delete()
            if deleted:
                return {'msg': 'KO, the configuration file of the Job is not well '
                        'formed', 'configuration file': config_file, 'warning':
                        'Old Job has been deleted'}, 409
            else:
                return {'msg': 'KO, the configuration file of the Job is not well '
                        'formed', 'configuration file': config_file}, 409

        rank = 0
        for required_arg in required_args:
            try:
                Required_Job_Argument(
                    name=required_arg['name'],
                    description=required_arg['description'],
                    type=required_arg['type'],
                    rank=rank,
                    job=job
                ).save()
                rank += 1
            except IntegrityError:
                job.delete()
                if deleted:
                    return {'msg': 'KO, the configuration file of the Job is not well '
                            'formed', 'configuration file': config_file, 'warning':
                            'Old Job has been deleted'}, 409
                else:
                    return {'msg': 'KO, the configuration file of the Job is not well '
                            'formed', 'configuration file': config_file}, 409

        for optional_arg in optional_args:
            try:
                Optional_Job_Argument(
                    name=optional_arg['name'],
                    flag=optional_arg['flag'],
                    type=optional_arg['type'],
                    description=optional_arg['description'],
                    job=job
                ).save()
            except IntegrityError:
                job.delete()
                return {'msg': 'KO, the configuration file of the Job is not well '
                        'formed', 'configuration file': config_file}, 409

        return {'msg': 'OK'}, 200

    def _action_install(self, names, addresses):
        """Install jobs on some agents"""

        severity = self.request.JSON.get('severity', 4)
        local_severity = self.request.JSON.get('local_severity', 4)

        return self._install_jobs(addresses, names, severity, local_severity)

    def _action_uninstall(self, names, addresses):
        """Uninstall jobs from some agents"""

        jobs = Job.objects.filter(pk__in=names)
        agents = Agent.objects.filter(pk__in=addresses)

        error_msg = []
        for agent in agents:
            for job in jobs:
                installed_job_name = '{} on {}'.format(job, agent)
                try:
                    installed_job = Installed_Job.objects.get(pk=installed_job_name)
                except ObjectDoesNotExist:
                    error_msg.append({
                        'error': 'No such job installed in the database',
                        'job_name': installed_job_name,
                    })
                    continue

                result = self._conductor_execute(
                        'uninstall_job {} "{}"'.format(agent.address, job.name))

                if result == 'OK':
                    installed_job.delete()
                else:
                    error_msg.append({
                        'error': 'Failed to uninstall a job',
                        'job_name': installed_job_name,
                    })

        if error_msg:
            return {'msg': error_msg}, 500
        else:
            return {'msg': 'OK'}, 200


class JobsView(BaseJobView):
    """Manage actions for jobs without an ID"""

    def get(self, request):
        """list all jobs"""

        verbosity = int(request.GET.get('verbosity', 0))
        try:
            address = request.GET['installed_on']
        except KeyError:
            return self._get_all_jobs(verbosity)
        else:
            update = self.GET.get('update', False)
            return self._get_installed_jobs(address, verbosity, update)

    def _get_all_jobs(self, verbosity):
        """list all the Jobs available on the benchmark"""

        response = {'jobs': []}
        for job in Job.objects.all():
            job_info = {'name': job.name}
            if verbosity:
                job_info['statistics'] = [
                        stat.name for stat in job.statistic_set.all()]
            response['jobs'].append(job_info)

        return response, 200

    def _get_installed_jobs(self, address, verbosity, update):
        """list all the Jobs installed on an Agent"""

        try:
            agent = Agent.objects.get(pk=address)
        except ObjectDoesNotExist:
            return {
                'msg': 'This Agent isn\'t in the database',
                'address': address,
            }, 404

        response = {'errors': [], 'agent': agent.address}
        if update:
            result = self._conductor_execute('update_jobs {}'.format(agent.address))
            if result.startswith('KO 1'):
                response['errors'].append({'error': result[5:]})
            elif result.startswith('KO 2'):
                response['errors'].append({
                    'jobs_name': result[5:],
                    'error': 'These Jobs aren\'t in the Job list of the Controller',
                })

        try:
            installed_jobs = agent.installed_job_set.all()
        except (KeyError, Installed_Job.DoesNotExist):
            response['installed_jobs'] = []
        else:
            response['installed_jobs'] = []
            for job in installed_jobs:
                job_infos = {
                    'name': job.job.name,
                    'update_status': job.update_status.astimezone(timezone.get_current_timezone()),
                }
                if verbosity > 0:
                    job_infos['severity'] = job.severity
                    job_infos['default_stat_policy'] = {
                        'storage': job.default_stat_storage,
                        'broadcast': job.default_stat_broadcast,
                    }
                if verbosity > 1:
                    job_infos['local_severity'] = job.local_severity
                    for statistic_instance in job.statistic_instance_set.all():
                        if 'statistic_instances' not in job_infos:
                            job_infos['statistic_instances'] = []
                        job_infos['statistic_instances'].append({
                            'name': statistic_instance.stat.name,
                            'storage': statistic_instance.storage,
                            'broadcast': statistic_instance.broadcast,
                        })
                response['installed_jobs'].append(job_infos)
        finally:
            return response, 200

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
                names = request.JSON['names']
            except KeyError:
                names = request.POST.getlist('name')

            try:
                addresses = request.JSON['addresses']
            except KeyError:
                addresses = request.POST.getlist('address')

            try:
                function = getattr(self, '_action_' + action)
            except KeyError:
                return {'msg': 'POST data malformed: unknown action '
                        '\'{}\' for this route'.format(action)}, 400

            if not isinstance(names, list):
                names = [names]
            if not isinstance(addresses, list):
                addresses = [addresses]

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

        try:
            job = Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            return {
                'msg': 'This Job isn\'t in the database',
                'job_name': name,
            }, 404

        return {'job_name': name, 'help': job.help}, 200

    def _status_stats(self, name):
        """compute statistics status for the given job"""

        verbosity = int(self.request.GET.get('verbosity', 0))

        try:
            job = Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            return {
                'msg': 'This Job isn\'t in the database',
                'job_name': name,
            }, 404

        result = {'job_name': name, 'statistics': []}
        for stat in job.statistic_set.all():
            statistic = {'name': stat.name}
            if verbosity > 0:
                statistic['description'] = stat.description
            if verbosity > 1:
                statistic['frequency'] = stat.frequency
            result['statistics'].append(statistic)

        return result, 200

    def put(self, request, name):
        """create a new job"""

        try:
            path = request.JSON['path']
        except KeyError:
            return {'msg': 'Data malformed: \'path\' missing'}, 400

        return self._create_job(name, path)

    def delete(self, request, name):
        """remove a job from the database"""

        try:
            job = Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            return {
                'msg': 'This Job isn\'t in the database',
                'job_name': name,
            }, 404

        job.delete()
        return {'msg': 'OK'}, 200

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
            severity = self.request.JSON['severity']
        except KeyError:
            return {'msg': 'POST data malformed: \'severity\' missing'}, 400

        try:
            address, = addresses
        except ValueError:
            return {'msg': 'POST data malformed: \'addresses\' should '
                    'contain 1 item for action \'log_severity\''}, 400

        name = '{} on {}'.format(name, address)
        try:
            installed_job = Installed_Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            return {
                'msg': 'This Installed_Job isn\'t in the database',
                'job_name': name,
            }, 404

        try:
            logs_job = Installed_Job.objects.get(pk='rsyslog_job on {}'.format(address))
        except ObjectDoesNotExist:
            return {
                'msg': 'The Installed_Job rsyslog isn\'t in the database',
                'job_name': 'logs on {}'.format(address),
            }, 404

        instance = Job_Instance(job=logs_job)
        instance.status = "starting ..."
        instance.update_status = timezone.now()

        date = self.request.JSON.get('date', 'now')
        if date == 'now':
            instance.start_date = timezone.now()
        else:
            start_date = datetime.fromtimestamp(
                    date / 1000,
                    tz=timezone.get_current_timezone())
            instance.start_date = start_date
        instance.periodic = False
        instance.save()

        instance_args = {'job_name': [name], 'instance_id': [instance.id]}
        date = self._job_instance_launcher(instance, instance_args, launch=False)

        result = self._conductor_execute(
                'set_job_log_severity {} {} {} {}'
                .format(
                    date,
                    instance.id, severity,
                    self.request.JSON.get(
                        'local_severity',
                        installed_job.local_severity)))
        response = {'msg': result}
        if result == 'KO':
            instance.delete()
            return response, 404
        instance.status = "Started"
        instance.update_status = timezone.now()
        instance.save()
        return response, 200

    def _action_stat_policy(self, names, addresses):
        """change statistics policy of a job"""

        name, = names
        try:
            address, = addresses
        except ValueError:
            return {'msg': 'POST data malformed: \'addresses\' should '
                    'contain 1 item for action \'stat_policy\''}, 404

        name = '{} on {}'.format(name, address)
        try:
            installed_job = Installed_Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            return {
                'msg': 'This Installed_Job isn\'t in the database',
                'job_name': name,
            }, 404

        request_data = self.request.JSON

        def set_storage_and_broadcast(stuff):
            try:
                storage = request_data['storage']
            except KeyError:
                pass
            else:
                stuff.storage = storage

            try:
                broadcast = request_data['broadcast']
            except KeyError:
                pass
            else:
                stuff.broadcast = broadcast

        try:
            stat_name = request_data['stat_name']
        except KeyError:
            set_storage_and_broadcast(installed_job)
        else:
            statistic = installed_job.job.statistic_set.filter(name=stat_name)[0]
            stat = Statistic_Instance.objects.filter(stat=statistic,
                                                     job=installed_job)
            if not stat:
                stat = Statistic_Instance(stat=statistic, job=installed_job)
            else:
                stat = stat[0]
            set_storage_and_broadcast(stat)

            if 'broadcast' in request_data or 'storage' in request_data:
                stat.save()
            else:
                # TODO check if the row exist in the DB before deleting
                # instead of catching an AssertionError
                try:
                    stat.delete()
                except AssertionError:
                    pass
        installed_job.save()

        rstat_name = 'rstats_job on {}'.format(address)
        try:
            rstats_job = Installed_Job.objects.get(pk=rstat_name)
        except ObjectDoesNotExist:
            return {
                'msg': 'The Installed_Job rstats isn\'t in the database',
                'job_name': rstat_name,
            }, 404

        instance = Job_Instance(job=rstats_job)
        instance.status = "starting ..."
        instance.update_status = timezone.now()

        date = request_data.get('date', 'now')
        if date == 'now':
            instance.start_date = timezone.now()
        else:
            start_date = datetime.fromtimestamp(
                    date / 1000,
                    tz=timezone.get_current_timezone())
            instance.start_date = start_date
        instance.periodic = False
        instance.save()

        instance_args = {'job_name': [name], 'instance_id': [instance.id]}
        date = self._job_instance_launcher(instance, instance_args, launch=False)
        result = self._conductor_execute(
                'set_job_stat_policy {} {}'
                .format(date, instance.id))
        response = {'msg': result}
        if result == 'KO':
            instance.delete()
            installed_job.save()
            return response, 404
        instance.status = "Started"
        instance.update_status = timezone.now()
        instance.save()

        return response, 200


class BaseInstanceView(GenericView):
    """Abstract base class used to factorize job instances management"""

    def _action_stop(self, ids):
        """stop the given job instances"""

        instances = Job_Instance.objects.filter(pk__in=ids)
        date = self.request.JSON.get('date', 'now')
        if date == 'now':
            stop_date = timezone.now()
        else:
            stop_date = datetime.fromtimestamp(
                    date / 1000,
                    tz=timezone.get_current_timezone())

        response = {'msg': 'OK', 'error': []}
        for instance in instances:
            instance.stop_date = stop_date
            instance.save()
            result = self._conductor_execute('stop_job_instance {} {}'.format(date, instance.id))
            if result == 'OK':
                if stop_date <= timezone.now():
                    instance.is_stopped = True
                    instance.save()
            else:
                response['msg'] = 'Something went wrong'
                response['error'].append({'msg': result, 'instance': instance.id})

        if response['error']:
            return response, 500
        else:
            return response, 200

    def _job_instance_status(self, installed_job, instance_id, data):
        """query the status of the given installed job"""

        try:
            watch = Watch.objects.get(pk=instance_id)
            if 'interval' not in data and 'stop' not in data:
                return {'msg': 'A Watch already exists in the database'}, 400
        except ObjectDoesNotExist:
            watch = Watch(job=installed_job, instance_id=instance_id, interval=0)

        should_delete_watch = True
        if 'interval' in data:
            should_delete_watch = False
            interval = int(data['interval'])
            watch.interval = interval
            cmd = 'status_job_instance interval {} {}'.format(interval, instance_id)
        elif 'stop' in data:
            cmd = 'status_job_instance stop {} {}'.format(data['stop'], instance_id)
        else:
            date = data.get('date', 'now')
            cmd = 'status_job_instance date {} {}'.format(date, instance_id)
        watch.save()

        result = self._conductor_execute(cmd)
        response = {'msg': result}
        if result == 'OK':
            if should_delete_watch:
                watch.delete()
            return response, 200
        else:
            watch.delete()
            return response, 500

    def _build_instance_infos(self, instance, update, verbosity):
        """Helper function to simplify `build_instances`"""

        instance_infos = {'id': instance.id, 'arguments': {}}
        if update:
            result = self._conductor_execute('update_instance {}'.format(instance.id))
            if result.startswith('KO'):
                instance_infos['error'] = result[3:]
            instance.refresh_from_db()

        for required_job_argument in instance.required_job_argument_instance_set.all():
            for value in required_job_argument.job_argument_value_set.all():
                if required_job_argument.argument.name not in instance_infos['arguments']:
                    instance_infos['arguments'][required_job_argument.argument.name] = []
                instance_infos['arguments'][required_job_argument.argument.name].append(value.value)

        for optional_job_argument in instance.optional_job_argument_instance_set.all():
            for value in optional_job_argument.job_argument_value_set.all():
                if optional_job_argument.argument.name not in instance_infos['arguments']:
                    instance_infos['arguments'][optional_job_argument.argument.name] = []
                instance_infos['arguments'][optional_job_argument.argument.name].append(value.value)

        if verbosity > 0:
            instance_infos['update_status'] = instance.update_status.astimezone(timezone.get_current_timezone())
            instance_infos['status'] = instance.status
        if verbosity > 1:
            instance_infos['start_date'] = instance.start_date.astimezone(timezone.get_current_timezone())
        if verbosity > 2:
            try:
                instance_infos['stop_date'] = instance.stop_date.astimezone(timezone.get_current_timezone())
            except AttributeError:
                instance_infos['stop_date'] = 'Not programmed yet'

        return instance_infos


class InstancesView(BaseInstanceView):
    """Manage actions on job instances without an ID"""

    def get(self, request):
        """list all job instances"""

        agents_ip = request.GET.getlist('address')

        update = request.GET.get('update', False)
        verbosity = int(request.GET.get('verbosity', 0))

        if not agents_ip:
            agents = Agent.objects.all()
        else:
            agents = Agent.objects.filter(pk__in=agents_ip)

        # TODO: check if prefetch_related works as expected
        response = {
            'instances': list(
                self._build_installed_jobs(
                    agents.prefetch_related('installed_job_set'),
                    update,
                    verbosity))
        }
        return response, 200

    def _build_installed_jobs(self, agents, update, verbosity):
        """Helper function to simplify listing all instances on an agent"""

        for agent in agents:
            installed_jobs = list(self._build_instances(
                agent.installed_job_set.all(),
                update,
                verbosity))
            if installed_jobs:
                yield {'address': agent.address, 'installed_jobs': installed_jobs}

    def _build_instances(self, jobs, update, verbosity):
        """Helper function to simplify `build_installed_jobs`"""

        for job in jobs:
            instances = [
                    self._build_instance_infos(job_instance, update, verbosity)
                    for job_instance in job.job_instance_set.filter(is_stopped=False)]
            if instances:
                yield {'job_name': job.name, 'instances': instances}

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
                ids = request.JSON['instance_ids']
            except KeyError:
                ids = request.POST.getlist('instance_id')
            return function(ids)

        return function()

    def _action_start(self):
        """start an instance of the given job on the given agent"""

        try:
            agent_ip = self.request.JSON['agent_ip']
            job_name = self.request.JSON['job_name']
        except KeyError as e:
            return {'msg': 'POST data malformed: {} missing'.format(e)}, 400

        try:
            instance_args = self.request.JSON['instance_args']
        except KeyError:
            instance_args = self.request.POST.getlist('instance_arg')

        name = '{} on {}'.format(job_name, agent_ip)
        try:
            installed_job = Installed_Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            return {
                'msg': 'This Installed_Job isn\'t in the database',
                'job_name': name,
            }, 404

        instance = Job_Instance(job=installed_job)

        return self._job_instance_launcher(instance, instance_args)


class InstanceView(BaseInstanceView):
    """Manage actions on specific job instances"""

    def get(self, request, id):
        """compute status of a job instance"""

        try:
            instance = Job_Instance.objects.get(pk=id)
        except ObjectDoesNotExist:
            return {'msg': 'No such job instance', 'instance_id': id}, 404

        verbosity = int(request.GET.get('verbosity', 0))

        return self._build_instance_infos(instance, True, verbosity)

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

        try:
            instance_args = self.request.JSON['instance_args']
        except KeyError:
            # Try to get them from a multivalue POST attribute
            instance_args = self.request.POST.getlist('instance_arg')

        try:
            instance = Job_Instance.objects.get(pk=id)
        except ObjectDoesNotExist:
            return {
                'msg': 'This Job Instance isn\'t in the database',
                'instance_id': id,
            }, 404

        return self._job_instance_launcher(instance, instance_args, restart=True)

    def _action_status(self, id):
        """start a status watch for the given job instance"""
        # try:
        #     agent_ip = self.request.JSON['agent_ip']
        #     job_name = self.request.JSON['job_name']
        # except KeyError as e:
        #     return {'msg': 'POST data malformed: missing {}'.format(e)}, 400

        # try:
        #     agent = Agent.objects.get(pk=agent_ip)
        # except ObjectDoesNotExist:
        #     return {
        #         'msg': 'This agent isn\'t in the database',
        #         'address': agent_ip,
        #     }, 404

        # try:
        #     job = Job.objects.get(pk=job_name)
        # except ObjectDoesNotExist:
        #     return {
        #         'msg': 'This job isn\'t in the database',
        #         'job_name': job_name,
        #     }, 404

        # name = '{} on {}'.format(job.name, agent.address)
        # try:
        #     installed_job = Installed_Job.objects.get(pk=name)
        # except ObjectDoesNotExist:
        #     return {
        #         'msg': 'This Installed_Job isn\'t in the database',
        #         'job_name': name,
        #     }, 404


        try:
            instance = Job_Instance.objects.get(pk=id)
        except ObjectDoesNotExist:
            return {'msg': 'No such job instance', 'instance_id': id}, 404

        return self._job_instance_status(instance.job, id, self.request.JSON)


class ScenariosView(GenericView):
    """Manage actions on scenarios without an ID"""

    def get(self, request):
        """list all scenarios"""

        self._debug()

    def post(self, request):
        """create a new scenario"""

        self._debug()


class ScenarioView(GenericView):
    """Manage action on specific scenario"""

    def get(self, request, name):
        """compute status of a scenario"""

        self._debug()

    def put(self, request, name):
        """modify a scenario"""

        self._debug()

    def delete(self, request, name):
        """remove a scenario from the database"""

        self._debug()


def push_file(request):
    try:
        uploaded_file = request.FILES['file']
        remote_path = request.POST['path']
        address = request.POST['agent_ip']
    except KeyError as e:
        return JsonResponse(
                status=400,
                data={'msg': 'POST data malformed: {} missing'.format(e)})

    try:
        agent = Agent.objects.get(pk=address)
    except ObjectDoesNotExist:
        return {
            'msg': 'This Agent isn\'t in the database',
            'address': address,
        }, 404

    # Copy file to disk
    path = '/tmp/{}'.format(uploaded_file.name)
    with open(path, 'wb') as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)

    result = GenericView._conductor_execute(
            'push_file {} {} {}'.format(uploaded_file.name, remote_path, address))
    response_data = {'msg': result}
    if result == 'OK':
        return JsonResponse(status=200, data=response_data)
    return JsonResponse(status=500, data=response_data)
