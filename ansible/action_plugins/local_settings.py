from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import textwrap

from ansible.module_utils._text import to_text, to_bytes
from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase
from ansible.plugins.filter.core import from_yaml

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


class ActionModule(ActionBase):
    def run(self, tmp=None, task_vars=None):
        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)

        args = self._task.args
        result['invocation'] = dict(module_args=args)
        try:
            chdir = args['path']
        except KeyError:
            result['failed'] = True
            result['changed'] = False
            result['msg'] = u'missing required arguments: path'
            return result
        cacheable = bool(args.pop('cacheable', False))

        command = """\
                from local_settings import *
                password = DATABASES['default']['PASSWORD']
                print([password, SECRET_KEY])"""
        password, key = self.remote_shell(result, command, chdir)

        if result['rc']:
            command = """\
                    from django.utils.crypto import get_random_string
                    chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
                    password = get_random_string(50, chars)
                    secret_key = get_random_string(50, chars)
                    print([password, secret_key])"""
            password, key = self.remote_shell(result, command)
            result['msg'] = u'local settings created'
            result['changed'] = True
        else:
            result['msg'] = u'local settings fetched'
            result['changed'] = False

        if result['rc']:
            result['failed'] = True
            result['msg'] = u'cannot create local settings parameters'
            return result

        facts = dict(
                openbach_local_settings_database_password=password,
                openbach_local_settings_secret_key=key,
        )

        result['ansible_facts'] = facts
        result['ansible_facts_cacheable'] = cacheable
        return result

    def remote_shell(self, result, command, chdir=None):
        script = ';'.join(textwrap.dedent(command).splitlines())
        shell = self._low_level_execute_command('python3 -c "{}"'.format(script), chdir=chdir)
        result.update(shell)
        result['stderr_lines'] = shell['stderr'].splitlines()
        if not result['rc']:
            return from_yaml(shell['stdout'].strip())
        return None, None
