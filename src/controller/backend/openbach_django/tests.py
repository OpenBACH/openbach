from django.test import TestCase
from django.utils import timezone

from .models import (
        Collector, Agent, Project, Network,
        Entity, Keyword, Job, OsCommand,
        Statistic, InstalledJob,
        StatisticInstance, JobInstance, Watch,
        RequiredJobArgument, OptionalJobArgument,
        RequiredJobArgumentValue,
        OptionalJobArgumentValue,
        Scenario, ScenarioInstance,
        ScenarioArgument, ScenarioConstant,
        ScenarioArgumentValue,
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
