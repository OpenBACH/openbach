# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2017-10-26 16:23
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


def create_scenarios_from_initial_version(apps, schema_editor):
    Scenario = apps.get_model('openbach_django', 'Scenario')
    ScenarioVersion = apps.get_model('openbach_django', 'ScenarioVersion')
    for initial_scenario in ScenarioVersion.objects.all():
        scenario = Scenario.objects.create(
                name=initial_scenario.name,
                description=initial_scenario.description,
                project=initial_scenario.project)
        initial_scenario.scenario = scenario
        initial_scenario.save()


class Migration(migrations.Migration):

    dependencies = [
        ('openbach_django', '0013_change_os_command'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Scenario',
            new_name='ScenarioVersion',
        ),
        migrations.RenameField(
            model_name='openbachfunction',
            old_name='scenario',
            new_name='scenario_version',
        ),
        migrations.RenameField(
            model_name='scenarioargument',
            old_name='scenario',
            new_name='scenario_version',
        ),
        migrations.RenameField(
            model_name='scenarioconstant',
            old_name='scenario',
            new_name='scenario_version',
        ),
        migrations.RenameField(
            model_name='scenarioinstance',
            old_name='scenario',
            new_name='scenario_version',
        ),
        migrations.AlterUniqueTogether(
            name='openbachfunction',
            unique_together=set([('scenario_version', 'function_id')]),
        ),
        migrations.AlterUniqueTogether(
            name='scenarioargument',
            unique_together=set([('name', 'scenario_version')]),
        ),
        migrations.AlterUniqueTogether(
            name='scenarioconstant',
            unique_together=set([('name', 'scenario_version')]),
        ),
        migrations.CreateModel(
            name='Scenario',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=500)),
                ('description', models.TextField(blank=True, null=True)),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='scenarios', to='openbach_django.Project')),
            ],
        ),
        migrations.AddField(
            model_name='scenarioversion',
            name='scenario',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='versions', to='openbach_django.Scenario'),
            preserve_default=False,
        ),
        migrations.RunPython(
            create_scenarios_from_initial_version,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='scenarioversion',
            name='scenario',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='versions', to='openbach_django.Scenario'),
        ),
        migrations.AlterUniqueTogether(
            name='scenarioversion',
            unique_together=set([]),
        ),
        migrations.RemoveField(
            model_name='scenarioversion',
            name='description',
        ),
        migrations.RemoveField(
            model_name='scenarioversion',
            name='name',
        ),
        migrations.RemoveField(
            model_name='scenarioversion',
            name='project',
        ),
        migrations.AlterUniqueTogether(
            name='scenario',
            unique_together=set([('name', 'project')]),
        ),
    ]
