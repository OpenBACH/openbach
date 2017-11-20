from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import sys
import tty
import errno
import termios
import textwrap
from os import isatty
from contextlib import contextmanager

from ansible.module_utils.six import PY3
from ansible.module_utils._text import to_text, to_bytes
from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase
from ansible.plugins.filter.core import from_yaml

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


def display_message(message, color=None):
    msg = to_bytes(message, encoding=display._output_encoding(stderr=False))
    if PY3:
        msg = to_text(msg, display._output_encoding(stderr=False), errors='replace')

    sys.stdout.write(msg)
    try:
        sys.stdout.flush()
    except IOError as e:
        if e.errno != errno.EPIPE:
            raise


@contextmanager
def terminal_context(stream):
    try:
        fd = stream.fileno()
    except (ValueError, AttributeError):
        raise AnsibleError('cannot ask user for credentials: stdin is closed!')

    if not isatty(fd):
        raise AnsibleError('cannot ask user for credentials: stdin is not a tty!')

    old_settings = None
    try:
        old_settings = termios.tcgetattr(fd)
        tty.setraw(fd)
        yield fd
    finally:
        if old_settings is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def get_user_input(prompt, stream):
    user_input = b''
    display_message(prompt)
    termios.tcflush(stream, termios.TCIFLUSH)
    while True:
        try:
            key_pressed = stream.read(1)
            if key_pressed == b'\x03':
                raise KeyboardInterrupt
            if key_pressed in (b'\r', b'\n'):
                display_message('\r\n')
                return user_input
            else:
                user_input += key_pressed
        except KeyboardInterrupt:
            raise AnsibleError('user requested abort!')


class ActionModule(ActionBase):
    def run(self, tmp=None, task_vars=None):
        if PY3:
            stdin = self._connection._new_stdin.buffer
        else:
            stdin = self._connection._new_stdin

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)

        args = self._task.args
        result['invocation'] = dict(module_args=args)
        try:
            cmd = '{} shell'.format(args['manager'])
        except KeyError:
            result['failed'] = True
            result['changed'] = False
            result['msg'] = u'missing required arguments: manager'
            return result
        if 'extra_args' in args:
            cmd = '{} {}'.format(cmd, args['extra_args'])
        cacheable = bool(args.pop('cacheable', False))
        username = task_vars.get('openbach_backend_admin_name')

        if username is not None:
            create_superuser = False
            user_provided_username = True
        else:
            user_provided_username = False

            # Retrieving the list of admin members
            # to check if we need to create it or not
            available_admins = self.remote_shell(result, cmd, """\
                    from django.contrib.auth.models import User
                    admins = User.objects.filter(is_staff=True)
                    admin_names = [user.get_username() for user in admins]
                    print(admin_names)""")
            create_superuser = not available_admins

            if create_superuser:
                display_message(
                        'OpenBACH needs that an administrator is '
                        'created before further processing\r\n')
            else:
                display_message('Please log in as an OpenBACH administrator\r\n')

            # Ask the user the name of the admin to use
            while True:
                with terminal_context(stdin) as fd:
                    settings = termios.tcgetattr(fd)
                    no_echo = settings[3]
                    settings[3] = (no_echo | termios.ECHO) & ~termios.ECHOCTL
                    termios.tcsetattr(fd, termios.TCSADRAIN, settings)
                    username = get_user_input('username: ', stdin)
                    username = to_text(username, errors='surrogate_or_strict')

                    if create_superuser or username in available_admins:
                        break

                    settings[3] = no_echo
                    termios.tcsetattr(fd, termios.TCSADRAIN, settings)
                    display_message('This user does not exist, create it? [Y/n] \r\n')
                    termios.tcflush(stdin, termios.TCIFLUSH)
                    if stdin.read(1).lower() != b'n':
                        create_superuser = True
                        break

        # Ask the user the password for the provided user
        # if they didn't already provided it
        password = None
        if user_provided_username:
            password = task_vars.get('openbach_backend_admin_password')
            if password is None:
                display_message(
                        'You chose to log in as \'{}\' for '
                        'administrative purposes\r\n'.format(username))
        if password is None:
            with terminal_context(stdin) as fd:
                password = get_user_input('password: ', stdin)
                password = to_text(password, errors='surrogate_or_strict')

        result['changed'] = create_superuser
        if create_superuser:
            self.remote_shell(result, cmd, """\
                    from django.contrib.auth.models import User
                    users = User.objects.filter(username='{0}').count()
                    User.objects.create_superuser('{0}', '', '{1}') if not users else exit(1)
                    """.format(username, password))
            if result['rc']:
                result['failed'] = True
                result['msg'] = u'cannot create user'
                return result
        else:
            # Checking that the user can connect and is, in fact, an admin
            response = self.remote_shell(result, cmd, """\
                    from django.contrib.auth.models import User
                    user = User.objects.filter(username='{}').last()
                    is_admin = user.is_staff if user else False
                    has_password = user.check_password('{}') if user else False
                    print([is_admin, has_password])""".format(username, password))

            if result['rc']:
                return result

            is_admin, has_password = response

            if not is_admin:
                result['failed'] = True
                result['msg'] = u'user is not an administrator'
                return result

            if not has_password:
                result['failed'] = True
                result['msg'] = u'wrong credentials for user'
                return result

        facts = dict(
                openbach_backend_admin_name=username,
                openbach_backend_admin_password=password,
        )

        result['msg'] = u'user is an administrator'
        result['failed'] = False
        result['ansible_facts'] = facts
        result['ansible_facts_cacheable'] = cacheable
        return result

    def remote_shell(self, result, command, piped_data):
        data = ';'.join(textwrap.dedent(piped_data).splitlines())
        shell = self._low_level_execute_command(command, in_data=data)
        result.update(shell)
        result['stderr_lines'] = shell['stderr'].splitlines()
        return from_yaml(shell['stdout'].strip('> \n'))
