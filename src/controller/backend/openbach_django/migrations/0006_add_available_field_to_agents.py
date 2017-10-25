# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2017-08-29 13:10
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('openbach_django', '0005_adapt_default_job_path_to_new_installation'),
    ]

    operations = [
        migrations.AddField(
            model_name='agent',
            name='available',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='agent',
            name='update_available',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
