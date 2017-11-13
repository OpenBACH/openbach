#!/usr/bin/python


import os

from ansible.module_utils.basic import AnsibleModule


ANSIBLE_METADATA = {
    'metadata_version': '0.1',
    'status': ['preview'],
    'supported_by': 'openbach'
}


DOCUMENTATION = '''
---
module: jobs_metadata

short_description: This module fetches metadata of jobs in the given folders

version_added: "2.4"

description:
    - "This module gathers the names and paths of jobs found in the given folders. It works by recursively searching for .yml files in a files subfolder and checking that the matching install_xxx.yml and uninstall_xxx.yml exist in the parent folder."

options:
    folders:
        description:
            - A list of the folders to search jobs into
        required: true
    substitute:
        description:
            - A path to substitute the root folder name by
        required: false
    limit:
        description:
            - Limit the collected informations to the ones of the jobs in this list
        required: false

author:
    - Mathias Ettinger (mathias.ettinger@toulouse.viveris.fr)
'''


EXAMPLES = '''
# Pass in folders
- name: Test with folders
  jobs_metadata:
    folders:
      - ../src/jobs
      - /opt/jobs

# pass in folders and have a substitute
- name: Test with folders and substitute
  jobs_metadata:
    folders:
      - ../src/jobs
      - /opt/jobs
    substitute: /opt/openbach/controller/src/jobs/

# pass in folders and have a limitating list
- name: Test with folders and limit
  jobs_metadata:
    folders:
      - ../src/jobs
      - /opt/jobs
    limit:
      - fping
      - netcat
      - iperf

# use all the parameters at once
- name: Test with folders, limit, and have a substitute
  jobs_metadata:
    folders:
      - ../src/jobs
      - /opt/jobs
    limit:
      - fping
      - netcat
      - iperf
    substitute: /opt/openbach/controller/src/jobs/

# fail the module
- name: Test failure of the module
  jobs_metadata:
    substitute: /opt/openbach/controller/src/jobs/
'''


RETURN = '''
openbach_jobs:
    description: A list of mapping containing the names and paths of the found jobs.
'''


def get_jobs_infos(folder):
    for root, folders, filenames in os.walk(folder):
        if os.path.basename(root) != 'files':
            continue

        for filename in filenames:
            name, ext = os.path.splitext(filename)
            if ext != '.yml':
                continue

            parent = os.path.dirname(root)
            install = os.path.join(parent, 'install_{}.yml'.format(name))
            uninstall = os.path.join(parent, 'uninstall_{}.yml'.format(name))
            if os.path.exists(install) and os.path.exists(uninstall):
                yield name, parent


def get_all_jobs_infos(folders, limit, substitute):
    limit = set(limit)
    for folder in folders:
        for name, path in get_jobs_infos(folder):
            if substitute:
                path = os.path.join(substitute, path[len(folder):])
            if not limit or name in limit:
                yield {'name': name, 'path': path}


def run_module():
    # define the available arguments/parameters that a user can pass to
    # the module
    module_args = dict(
        folders=dict(type='list', required=True),
        substitute=dict(type='str', required=False, default=None),
        limit=dict(type='list', required=False, default=[]),
    )

    # seed the result dict in the object
    # we primarily care about changed and state
    # change is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = dict(
        changed=False,
        openbach_jobs=[],
    )

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        return result

    # manipulate or modify the state as needed
    jobs = get_all_jobs_infos(
            module.params['folders'],
            module.params['limit'],
            module.params['substitute'])
    result['openbach_jobs'] = list(jobs)

    module.exit_json(**result)


if __name__ == '__main__':
    run_module()
