# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2017-07-10 15:15
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('openbach_django', '0003_alter_installed_job'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='agent',
            name='password',
        ),
        migrations.RemoveField(
            model_name='agent',
            name='username',
        ),
        migrations.RemoveField(
            model_name='collector',
            name='password',
        ),
        migrations.RemoveField(
            model_name='collector',
            name='username',
        ),
        migrations.AddField(
            model_name='collector',
            name='logs_database_name',
            field=models.CharField(default='openbach', max_length=500),
        ),
        migrations.AddField(
            model_name='collector',
            name='logstash_broadcast_mode',
            field=models.CharField(choices=[('udp', 'UDP'), ('tcp', 'TCP')], default='udp', max_length=3),
        ),
        migrations.AddField(
            model_name='collector',
            name='logstash_broadcast_port',
            field=models.IntegerField(default=2223),
        ),
    ]