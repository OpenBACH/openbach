import json

from django.test import TestCase
from django.utils import timezone

from .models import (
        Collector, Agent, Project, Job,
        InstalledJob, RequiredJobArgument,
        OptionalJobArgument, JobInstance,
)


class JobTestCase(TestCase):
    def setUp(self):
        Job.objects.create(name='test_job')

    def test_arguments_create(self):
        job = Job.objects.get(name='test_job')
        arg = RequiredJobArgument.objects.create(
                name='first', type='int', job=job,
                count='1', rank=0)
        self.assertTrue(arg.check_count(1))
        self.assertFalse(arg.check_count(0))
        for i in range(2, 10):
            self.assertFalse(arg.check_count(i))

        arg = RequiredJobArgument.objects.create(
                name='second', type='str', job=job,
                count='3-6', rank=1)
        for i in range(3, 7):
            self.assertTrue(arg.check_count(i))
        for i in range(3):
            self.assertFalse(arg.check_count(i))
        for i in range(7, 10):
            self.assertFalse(arg.check_count(i))

        with self.assertRaises(TypeError):
            RequiredJobArgument.objects.create(
                    name='third', type='ip', job=job,
                    count='+', rank=2)

        arg = OptionalJobArgument.objects.create(
                name='optional', type='bool', job=job,
                count='*', flag='-o')
        for i in range(10):
            self.assertTrue(arg.check_count(i))

        OptionalJobArgument.objects.create(
                name='flags', type='None', job=job,
                count='0', flag='-f')

        OptionalJobArgument.objects.create(
                name='star', type='int', job=job,
                count='*', flag='-s')

        self.assertEqual(job.required_arguments.count(), 2)
        self.assertEqual(job.optional_arguments.count(), 3)


class InstalledJobTestCase(TestCase):
    def setUp(self):
        Job.objects.create(name='test_job')
        collector = Collector.objects.create(
                address='172.20.34.45',
                username='openbach',
                password='openbach')
        Agent.objects.create(
                address='172.20.34.45', name='Openbach_Agent',
                reachable=True, username='openbach',
                password='openbach', collector=collector)

    def test_install_job(self):
        agent = Agent.objects.get(name='Openbach_Agent')
        job = Job.objects.get(name='test_job')
        installed_job = InstalledJob.objects.create(
                agent=agent, job=job,
                severity=1, local_severity=1)
        self.assertEqual(installed_job.job, job)
        self.assertEqual(installed_job.agent, agent)


class JobInstanceTestCase(TestCase):
    def setUp(self):
        job = Job.objects.create(name='test_job')
        collector = Collector.objects.create(
                address='172.20.34.45',
                username='openbach',
                password='openbach')
        agent = Agent.objects.create(
                address='172.20.34.45', name='Openbach_Agent',
                reachable=True, username='openbach',
                password='openbach', collector=collector)
        InstalledJob.objects.create(
                agent=agent, job=job,
                severity=1, local_severity=1)
        RequiredJobArgument.objects.create(
                name='first', type='int', job=job,
                count='1', rank=0)
        RequiredJobArgument.objects.create(
                name='second', type='str', job=job,
                count='3-6', rank=1)
        OptionalJobArgument.objects.create(
                name='optional', type='bool', job=job,
                count='*', flag='-o')
        OptionalJobArgument.objects.create(
                name='flags', type='None', job=job,
                count='0', flag='-f')
        OptionalJobArgument.objects.create(
                name='star', type='int', job=job,
                count='*', flag='-s')

    def test_job_instance(self):
        now = timezone.now()
        installed_job = InstalledJob.objects.all()[0]
        job_instance = JobInstance.objects.create(
                job=installed_job,
                update_status=now,
                start_date=now,
                periodic=False)

        job_instance.configure({
            'first': 42,
            'second': ['riri', 'fifi', 'loulou'],
            'optional': [True, False, True, True, False],
        })
        job_instance.save()


class ProjectTestCase(TestCase):
    def setUp(self):
        self.project_json = {
                "name": "OpenSAND",
                "description": "OpenSAND Plateform",
                "entity": [{
                    "name": "Sat",
                    "description": "The satellite",
                    "agent": {
                        "name": "openbach-controller",
                        "address": "172.20.34.39",
                        "username": "opensand",
                        "collector": "172.20.34.39",
                    },
                    "networks": ["emu"],
                }, {
                    "name": "gw",
                    "description": "Gateway",
                    "agent": None,
                    "networks": ["emu", "lan_gw"],
                }, {
                    "name": "st1",
                    "description": "Satellite terminal 1",
                    "agent": None,
                    "networks": ["emu", "lan_st"],
                }, {
                    "name": "st2",
                    "description": "Satellite terminal 2",
                    "agent": None,
                    "networks": ["emu"],
                }, {
                    "name": "ws1",
                    "description": "Workstation 1",
                    "agent": None,
                    "networks": ["lan_st"],
                }, {
                    "name": "ws2",
                    "description": "Workstation 2",
                    "agent": None,
                    "networks": ["lan_st"],
                }, {
                    "name": "ws3",
                    "description": "Workstation 3",
                    "agent": None,
                    "networks": ["lan_gw"],
                }, {
                    "name": "ws4",
                    "description": "Workstation 4",
                    "agent": None,
                    "networks": []
                }],
                "network": ["emu", "lan_gw", "lan_st"],
                "scenario": [{
                    "name": "Ping between machines",
                    "description": "First scenario (for test)",
                    "arguments": {},
                    "constants": {},
                    "openbach_functions": [{
                        "id": 1,
                        "start_job_instance": {
                            "agent_ip": "172.20.34.39",
                            "fping": {
                                "destination_ip": "172.20.0.83",
                            },
                            "offset": 5,
                        },
                        "wait": {
                            "time": 5,
                        },
                    }, {
                        "id": 2,
                        "start_job_instance": {
                            "agent_ip": "172.20.34.39",
                            "hping": {
                                "destination_ip": "172.20.0.83",
                            },
                            "offset": 5,
                        },
                        "wait": {
                            "time": 5,
                        },
                    }],
                }, {
                    "name": "Congestion tests",
                    "description": "2 Iperf servs queried by 2 iperf clients",
                    "arguments": {},
                    "constants": {},
                    "openbach_functions": [{
                        "id": 1,
                        "start_job_instance": {
                            "agent_ip": "192.168.0.2",
                            "pep": {
                                "sat_network": "opensand",
                                "pep_port": 3000,
                            },
                            "offset": 0,
                        },
                    }, {
                        "id": 2,
                        "start_job_instance": {
                            "agent_ip": "192.168.0.7",
                            "iperf": {
                                "mode": "-s",
                                "udp": True,
                                "port": 5000,
                            },
                            "offset": 0,
                        },
                    }, {
                        "id": 3,
                        "start_job_instance": {
                            "agent_ip": "192.168.0.7",
                            "iperf": {
                                "mode": "-s",
                                "port": 5001,
                            },
                            "offset": 0,
                        },
                    }, {
                        "id": 4,
                        "start_job_instance": {
                            "agent_ip": "192.168.0.7",
                            "tcpprobe_monitoring": {
                                "port": 5001,
                                "interval": 10,
                                "path": "/tcp/tcpprobe.out",
                            },
                            "offset": 0,
                        },
                    }, {
                        "id": 5,
                        "start_job_instance": {
                            "agent_ip": "192.168.0.7",
                            "rate_monitoring": {
                                "interval": 1,
                                "chain": "-A INPUT",
                                "jump": "ACCEPT",
                                "in_interface": "eth0",
                                "protocol": "tcp",
                                "source_port": 5001,
                            },
                            "offset": 0,
                        },
                    }, {
                        "id": 6,
                        "start_job_instance": {
                            "agent_ip": "192.168.0.5",
                            "iperf": {
                                "mode": "-c 192.168.0.7",
                                "udp": True,
                                "port": 5000,
                            },
                            "offset": 0,
                        },
                        "wait": {
                            "time": 5,
                            "launched_ids": [1, 2, 3, 4, 5],
                        },
                    }, {
                        "id": 7,
                        "start_job_instance": {
                            "agent_ip": "192.168.0.5",
                            "iperf": {
                                "mode": "-c 192.168.0.7",
                                "port": 5001,
                            },
                            "offset": 0,
                        },
                        "wait": {
                            "time": 5,
                            "launched_ids": [1, 2, 3, 4, 5],
                        },
                    }, {
                        "id": 8,
                        "stop_job_instances": {
                            "openbach_function_ids": [5, 6],
                        },
                        "wait": {
                            "time": 500,
                            "launched_ids": [6, 7],
                        },
                    }, {
                        "id": 9,
                        "stop_job_instances": {
                            "openbach_function_ids": [1, 2, 3, 4, 5],
                        },
                        "wait": {
                            "launched_ids": [8],
                        },
                    }],
                }],
        }

    def _create_jobs(self):
        Job.objects.create(name='fping')
        Job.objects.create(name='hping')

    def _create_arguments(self):
        for job in Job.objects.filter(name__iendswith='ping'):
            RequiredJobArgument.objects.create(
                    job=job, rank=0, name='destination_ip',
                    type='ip', count='1')

    def _create_scenario_prerequisites(self):
        # Scenario 1
        self._create_jobs()
        self._create_arguments()

        # Scenario 2
        pep = Job.objects.create(name='pep')
        iperf = Job.objects.create(name='iperf')
        tcp = Job.objects.create(name='tcpprobe_monitoring')
        rate = Job.objects.create(name='rate_monitoring')

        RequiredJobArgument.objects.create(
                job=pep, rank=0, name='sat_network',
                type='str', count='1')
        OptionalJobArgument.objects.create(
                job=pep, flag='-p', name='pep_port',
                type='int', count='1')

        OptionalJobArgument.objects.create(
                job=iperf, flag='-s', name='mode',
                type='None', count='0')
        OptionalJobArgument.objects.create(
                job=iperf, flag='-u', name='udp',
                type='None', count='0')
        OptionalJobArgument.objects.create(
                job=iperf, flag='-p', name='port',
                type='int', count='1')

        RequiredJobArgument.objects.create(
                job=tcp, rank=0, name='port',
                type='int', count='1')
        OptionalJobArgument.objects.create(
                job=tcp, flag='-i', name='interval',
                type='int', count='1')
        OptionalJobArgument.objects.create(
                job=tcp, flag='-p', name='path',
                type='str', count='1')

        RequiredJobArgument.objects.create(
                job=rate, rank=0, name='interval',
                type='int', count='1')
        RequiredJobArgument.objects.create(
                job=rate, rank=1, name='chain',
                type='str', count='1')
        OptionalJobArgument.objects.create(
                job=rate, flag='-j', name='jump',
                type='str', count='1')
        OptionalJobArgument.objects.create(
                job=rate, flag='-i', name='in_interface',
                type='str', count='1')
        OptionalJobArgument.objects.create(
                job=rate, flag='-p', name='protocol',
                type='str', count='1')
        OptionalJobArgument.objects.create(
                job=rate, flag='--sport', name='source_port',
                type='int', count='1')

    def _test_project_fails_and_get_context_manager(self):
        name = self.project_json['name']
        description = self.project_json['description']
        project = Project.objects.create(name=name, description=description)
        with self.assertRaises(Project.MalformedError) as cm:
            project.load_from_json(self.project_json)
        return cm

    def test_scenario_fail_with_no_job(self):
        cm = self._test_project_fails_and_get_context_manager()
        self.assertEqual(
                cm.exception.error['section'],
                'scenario.Ping between machines')
        self.assertEqual(
                cm.exception.error['message']['error'],
                'No such job in the database')
        self.assertEqual(
                cm.exception.error['message']['offending_entry'],
                'openbach_functions.0.start_job_instance.fping')

    def test_scenario_fail_with_no_job_argument(self):
        self._create_jobs()
        cm = self._test_project_fails_and_get_context_manager()
        self.assertEqual(
                cm.exception.error['section'],
                'scenario.Ping between machines')
        self.assertEqual(
                cm.exception.error['message']['error'],
                'The configured job does not accept the given argument')
        self.assertEqual(
                cm.exception.error['message']['offending_entry'],
                'openbach_functions.0.start_job_instance.fping.destination_ip')

    def test_scenario_succed_with_job_arguments_but_second_fail(self):
        self._create_jobs()
        self._create_arguments()
        cm = self._test_project_fails_and_get_context_manager()
        self.assertEqual(
                cm.exception.error['section'],
                'scenario.Congestion tests')
        self.assertEqual(
                cm.exception.error['message']['error'],
                'No such job in the database')
        self.assertEqual(
                cm.exception.error['message']['offending_entry'],
                'openbach_functions.0.start_job_instance.pep')

    def test_success(self):
        self._create_scenario_prerequisites()
        name = self.project_json['name']
        description = self.project_json['description']
        project = Project.objects.create(name=name, description=description)
        project.load_from_json(self.project_json)
        # Check that the conductor will be able to send data back in the fifo
        json.dumps(project.json)
