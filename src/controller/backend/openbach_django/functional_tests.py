import unittest
import ipaddress

from django.test import TestCase
from .models import Job

import openbach_conductor as conductor


def get_valid_ip():
    ip = input('IP of testing agent> ')
    try:
        return ipaddress.ip_address(ip).compressed
    except ValueError:
        return


def get_content(name, default='openbach'):
    prompt = '{} (leave blank for \'{}\')> '.format(name, default)
    content = input(prompt)
    if not content:
        return default
    return content


TEST_MACHINE = get_valid_ip()
USERNAME = get_content('username')
PASSWORD = get_content('password')


class JobTestCase(TestCase):
    def setUp(self):
        Job.objects.create(name='test_job')

    def test_list_job(self):
        jobs, code = conductor.ListJobs().action()
        self.assertEqual(code, 200)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['general']['name'], 'test_job')


@unittest.skipIf(TEST_MACHINE is None, 'No agent specified')
class InstallTestCase(TestCase):
    def test_add_collector(self):
        response, code = conductor.AddCollector(
                TEST_MACHINE, USERNAME,
                PASSWORD, 'Collector').action()
        self.assertEqual(response, {})
        self.assertEqual(code, 204)
