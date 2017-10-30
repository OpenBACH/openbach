#!/usr/bin/env python

# OpenBACH is a generic testbed able to control/configure multiple
# network/physical entities (under test) and collect data from them. It is
# composed of an Auditorium (HMIs), a Controller, a Collector and multiple
# Agents (one for each network entity that wants to be tested).
#
#
# Copyright © 2016 CNES
#
#
# This file is part of the OpenBACH testbed.
#
#
# OpenBACH is a free software : you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see http://www.gnu.org/licenses/.


"""Base classes to help build a complete Database model"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''


import json
import shlex
import string
import ipaddress

from django.db import models
from django.core.exceptions import ValidationError

from .utils import check_and_get_value, ValuesType


class OpenbachFunctionArgument(models.CharField):
    """Custom field type to ease usage of placeholders in parameters values"""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 500)
        self.type = kwargs.pop('type', type(None))
        kwargs['default'] = None
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        """Return enough information to recreate the field as a 4-tuple;
        for serialization purposes (migrations).
        """
        name, path, args, kwargs = super().deconstruct()
        kwargs['type'] = self.type
        del kwargs['default']
        if kwargs['max_length'] == 500:
            del kwargs['max_length']
        return name, path, args, kwargs

    @staticmethod
    def placeholders(value):
        if not isinstance(value, str):
            return

        templated = string.Template(value)
        for match in templated.pattern.finditer(templated.template):
            escaped, named, braced, invalid = match.groups()
            if invalid is not None:
                raise ValidationError(
                        'value uses the placeholder escape '
                        'symbol ($) but does not provide a '
                        'valid identifier', code='invalid_template')
            if named is not None:
                yield named
            if braced is not None:
                yield braced

    @staticmethod
    def has_placeholders(value):
        placeholders = False
        for _ in OpenbachFunctionArgument.placeholders(value):
            placeholders = True
        return placeholders

    def validate_openbach_value(self, value, parameters):
        """Interpolate placeholders of the stored value to
        provide the actual value of this field.
        """
        if not self.has_placeholders(value):
            return value

        templated = string.Template(value)
        try:
            value = templated.substitute(parameters)
        except KeyError as e:
            raise ValidationError(
                    'value contains a placeholder (%(key)s) '
                    'that is not found in provided parameters',
                    code='invalid_placeholder',
                    params={'key': str(e)})
        except ValueError as e:
            raise ValidationError(
                    'value contains an invalid placeholder',
                    code='invalid_placeholder')

        return self._convert_from_db_value(value)

    def from_db_value(self, value, *args):
        """Convert a value from the database into its Python counterpart"""
        if value is None:
            return value

        if self.has_placeholders(value):
            return value

        return self._convert_from_db_value(value)

    def _convert_from_db_value(self, value):
        """Helper function that perform the actual convertion between
        database values and Python values.
        """
        try:
            if self.type == dict:
                return json.loads(value)
            if self.type == list:
                return shlex.split(value)
            if self.type == ipaddress._BaseAddress:
                return ipaddress.ip_address(value)
            if self.type == bool:
                return {'True': True, 'False': False}[value]
            return self.type(value)
        except (ValueError, KeyError):
            raise ValidationError(
                    'value is an invalid %(expected_type)s',
                    code='invalid',
                    params={'expected_type': self.type.__name__})

    def to_python(self, value):
        """Convert the value of this field into its Python representation"""
        if value is None or isinstance(value, self.type):
            return value

        if not isinstance(value, str):
            raise ValidationError(
                    'value has an invalid type \'%(real_type)s\' '
                    'should be \'%(expected_type)s\'',
                    code='invalid_type',
                    params={
                        'real_type': value.__class__.__name__,
                        'expected_type': self.type.__name__,
                    })

        return self.from_db_value(value)

    def get_prep_value(self, value):
        """Prepare the value so it can be inserted in the database"""
        # Do not let CharField prepare the value (cast to str) or
        # you won't be able to parse it back for lists and dicts
        value = super(models.CharField, self).get_prep_value(value)
        if value is None:
            return value
        value = self.to_python(value)
        if self.type == dict:
            return json.dumps(value)
        if self.type == list:
            return ' '.join(shlex.quote(str(val)) for val in value)
        return str(value)


class ContentTyped(models.Model):
    """Abstract base class for tables acting as abstract base classes.

    A ContentTyped class usually have several concrete implementations
    that are hard to retrieve at runtime so this class help to remember
    which concrete class was used to build the actual object.
    """

    content_model = models.CharField(editable=False, max_length=50, null=True)

    class Meta:
        abstract = True

    def concrete_base(self):
        """Inspect the inheritance chain and retrieve the
        first class in the hierarchy that is a subclass of
        ContentTyped but is not marked abstract.
        """
        klass = self.__class__
        for kls in reversed(klass.__mro__):
            if issubclass(kls, ContentTyped) and not kls._meta.abstract:
                return kls
        return klass

    def set_content_model(self):
        """Set content_model to the child class's related name,
        or None if this is the base class.
        """
        is_base_class = self.concrete_base() == self.__class__
        self.content_model = (
            None if is_base_class else self._meta.object_name.lower())

    def get_content_model(self):
        """Return content model, or an error if it is the base class"""
        if self.content_model:
            return getattr(self, self.content_model)
        raise NotImplementedError


class ArgumentValue(models.Model):
    """Data stored as the value of an Argument"""

    argument_value_id = models.AutoField(primary_key=True)
    value = models.CharField(max_length=500)

    def _check_and_set_value(self, value, value_type):
        self.value = check_and_get_value(value, value_type)

    def __str__(self):
        return self.value


class Argument(models.Model):
    """Data associated to a generic Argument"""

    CHOICES = tuple((t.value, t.name) for t in ValuesType)

    type = models.CharField(max_length=5, choices=CHOICES,
                            default=ValuesType.NONE_TYPE.value)
    count = models.CharField(max_length=11, null=True, blank=True)
    name = models.CharField(max_length=500)
    description = models.TextField(null=True, blank=True)

    class Meta:
        abstract = True

    def check_count(self, count):
        if self.type == ValuesType.NONE_TYPE or self.count == '*':
            return True
        if self.count == '+':
            return count > 0
        counts = [int(c) for c in self.count.split('-')]
        if len(counts) == 2:
            return counts[0] <= count <= counts[1]
        return count == counts[0]

    def save(self, *args, **kwargs):
        if self.count not in ('*', '+', None):
            try:
                counts = [int(x) for x in self.count.split('-')]
            except ValueError:
                raise TypeError(
                        'The count value of the argument \'{}\' should '
                        'be \'*\', \'+\', an integer or a range (two '
                        'integers separated by a dash)'.format(self.name))
            if len(counts) > 2:
                raise TypeError(
                        'When using a range as the count value of the '
                        'argument \'{}\', only 2 integers can be specified'
                        .format(self.name))

            try:
                low, high = counts
            except ValueError:
                pass  # A single integer was specified
            else:
                if low >= high:
                    raise TypeError(
                            'When using a range as the count value of the '
                            'argument \'{}\', the second integer should be '
                            'greater than the first one'.format(self.name))
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
