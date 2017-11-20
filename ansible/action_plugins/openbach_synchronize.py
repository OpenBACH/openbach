from ansible.plugins.action.synchronize import ActionModule as SynchronizeModule


class ActionModule(SynchronizeModule):
    def _get_absolute_path(self, path):
        if not path.startswith('rsync://'):
            original_path = path

            path = self._find_needle('files', path)

            if original_path and original_path[-1] == '/' and path[-1] != '/':
                # For rsync consistent behaviour, make sure the path ends
                # in a trailing "/" if the original path did
                path += '/'

        return path
