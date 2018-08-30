# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2018-07-31 15:56
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('openbach_django', '0022_fix_openbach_functions_models'),
    ]

    operations = [
        migrations.AlterField(
            model_name='job',
            name='path',
            field=models.FilePathField(allow_files=False, allow_folders=True, max_length=500, path='/opt/openbach/controller/src/jobs', recursive=True),
        ),
    ]
