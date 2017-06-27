from django.test import TestCase

import openbach_conductor as conductor


class NilTestCase(TestCase):
    def test_nothing(self):
        print('Hello, world!')
        self.assertTrue(True)
