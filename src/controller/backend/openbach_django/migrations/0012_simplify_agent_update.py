# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2017-10-19 10:06
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('openbach_django', '0011_add_owners'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='agentcommandresult',
            name='status_retrieve_status_agent',
        ),
    ]
