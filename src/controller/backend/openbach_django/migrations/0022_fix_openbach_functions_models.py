# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2017-12-18 10:10
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import openbach_django.base_models


class Migration(migrations.Migration):

    dependencies = [
        ('openbach_django', '0021_allow_dns_name_as_agent_ip'),
    ]

    operations = [
        migrations.CreateModel(
            name='AssignCollector',
            fields=[
                ('openbachfunction_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='openbach_django.OpenbachFunction')),
                ('address', openbach_django.base_models.OpenbachFunctionArgument(type=str)),
                ('collector', openbach_django.base_models.OpenbachFunctionArgument(type=str)),
            ],
            options={
                'abstract': False,
            },
            bases=('openbach_django.openbachfunction',),
        ),
        migrations.CreateModel(
            name='StopJobInstance',
            fields=[
                ('openbachfunction_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='openbach_django.OpenbachFunction')),
                ('openbach_function_id', openbach_django.base_models.OpenbachFunctionArgument(type=int)),
            ],
            options={
                'abstract': False,
            },
            bases=('openbach_django.openbachfunction',),
        ),
        migrations.RemoveField(
            model_name='addjob',
            name='openbachfunction_ptr',
        ),
        migrations.RemoveField(
            model_name='deletejob',
            name='openbachfunction_ptr',
        ),
        migrations.RemoveField(
            model_name='gethelpjob',
            name='openbachfunction_ptr',
        ),
        migrations.RemoveField(
            model_name='getstatisticsjob',
            name='openbachfunction_ptr',
        ),
        migrations.RemoveField(
            model_name='installjobs',
            name='openbachfunction_ptr',
        ),
        migrations.RemoveField(
            model_name='listagent',
            name='openbachfunction_ptr',
        ),
        migrations.RemoveField(
            model_name='listinstalledjobs',
            name='openbachfunction_ptr',
        ),
        migrations.RemoveField(
            model_name='listjobs',
            name='openbachfunction_ptr',
        ),
        migrations.RemoveField(
            model_name='retrievestatusagents',
            name='openbachfunction_ptr',
        ),
        migrations.RemoveField(
            model_name='retrievestatusjobs',
            name='openbachfunction_ptr',
        ),
        migrations.RemoveField(
            model_name='listjobinstances',
            name='verbosity',
        ),
        migrations.RemoveField(
            model_name='pushfile',
            name='agent_ip',
        ),
        migrations.RemoveField(
            model_name='statusjobinstance',
            name='verbosity',
        ),
        migrations.AddField(
            model_name='pushfile',
            name='address',
            field=openbach_django.base_models.OpenbachFunctionArgument(type=str),
        ),
        migrations.AlterField(
            model_name='installagent',
            name='address',
            field=openbach_django.base_models.OpenbachFunctionArgument(type=str),
        ),
        migrations.AlterField(
            model_name='installagent',
            name='collector',
            field=openbach_django.base_models.OpenbachFunctionArgument(type=str),
        ),
        migrations.AlterField(
            model_name='setlogseverityjob',
            name='address',
            field=openbach_django.base_models.OpenbachFunctionArgument(type=str),
        ),
        migrations.AlterField(
            model_name='setstatisticspolicyjob',
            name='address',
            field=openbach_django.base_models.OpenbachFunctionArgument(type=str),
        ),
        migrations.AlterField(
            model_name='uninstallagent',
            name='address',
            field=openbach_django.base_models.OpenbachFunctionArgument(type=str),
        ),
        migrations.DeleteModel(
            name='AddJob',
        ),
        migrations.DeleteModel(
            name='DeleteJob',
        ),
        migrations.DeleteModel(
            name='GetHelpJob',
        ),
        migrations.DeleteModel(
            name='GetStatisticsJob',
        ),
        migrations.DeleteModel(
            name='InstallJobs',
        ),
        migrations.DeleteModel(
            name='ListAgent',
        ),
        migrations.DeleteModel(
            name='ListInstalledJobs',
        ),
        migrations.DeleteModel(
            name='ListJobs',
        ),
        migrations.DeleteModel(
            name='RetrieveStatusAgents',
        ),
        migrations.DeleteModel(
            name='RetrieveStatusJobs',
        ),
    ]
