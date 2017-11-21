# -*- coding: utf-8 -*-
# Generated by Django 1.9.7 on 2017-11-21 13:44
from __future__ import unicode_literals

from django.db import migrations, models


def populate_version_from_job(apps, schema_editor):
    InstalledJob = apps.get_model('openbach_django', 'InstalledJob')
    for installed_job in InstalledJob.objects.all():
        installed_job.job_version = installed_job.job.job_version 
        installed_job.save()


class Migration(migrations.Migration):

    dependencies = [
        ('openbach_django', '0017_added_potential_networks'),
    ]

    operations = [
        migrations.AddField(
            model_name='installedjob',
            name='job_version',
            field=models.CharField(max_length=500, null=True),
        ),
        migrations.RunPython(
            populate_version_from_job,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='installedjob',
            name='job_version',
            field=models.CharField(max_length=500),
        ),
    ]
