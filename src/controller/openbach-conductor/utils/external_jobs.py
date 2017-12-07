import os
from contextlib import suppress

import yaml
import requests

PROJECT_ID = 102  # Internal ID of the openbach/openbach-external-jobs
TOKEN_HEADER = {
        # Access Token of the anonymous user of the net4sat gitlab
        'PRIVATE-TOKEN': 'UyAzSGgGPJKkc7MvMLo8',
}
BASE_URL = 'https://forge.net4sat.org/api/v3/projects/{}'.format(PROJECT_ID)

def read_proxies(group_vars_file):
    with open(group_vars_file) as openbach_variables:
        variables = yaml.load(openbach_variables)

    proxies = {}
    proxy_configuration = variables.get('openbach_proxy_env', {})
    for protocol in ('http', 'https'):
        with suppress(KeyError):
            proxies[protocol] = proxy_configuration['{}_proxy'.format(protocol)]

    return proxies

PROXIES = read_proxies('/opt/openbach/controller/ansible/group_vars/all')

def list_jobs_names():
    filenames = {
            f['path']
            for f in _list_project_files()
            if os.path.splitext(f['path'])[1] == '.yml'
    }

    return [
            {
                'display': ' '.join(map(str.title, name.split('_'))),
                'name': name,
            } for name in _list_jobs_names(filenames)
    ]

def add_job(name, src_dir='/opt/openbach/controller/src/jobs/private_jobs/'):
    yaml = '{}.yml'.format(name)
    project_files = _list_project_files()
    try:
        file_blob = next(
                f for f in project_files
                if os.path.basename(f['path']) == yaml
        )
    except StopIteration:
        return

    base_directory = os.path.dirname(os.path.dirname(file_blob['path']))
    for blob in project_files:
        path = blob['path']
        if path.startswith(base_directory) and blob['type'] == 'blob':
            _retrieve_file(path, os.path.join(src_dir, path))

    return os.path.join(src_dir, base_directory)

def _list_jobs_names(files):
    for filename in files:
        folder, filename = os.path.split(filename)
        job_name, _ = os.path.splitext(filename)
        parent_folder = os.path.dirname(folder)
        install = os.path.join(parent_folder, 'install_{}.yml'.format(job_name))
        uninstall = os.path.join(parent_folder, 'uninstall_{}.yml'.format(job_name))
        if install in files and uninstall in files:
            yield job_name

def _retrieve_file(file_path, dest_file):
    response = _do_request('/repository/blobs/HEAD', filepath=file_path)
    response.raise_for_status()

    dest_folder = os.path.dirname(dest_file)
    os.makedirs(dest_folder, exist_ok=True)

    with open(dest_file, 'wb') as f:
        f.write(response.content)

def _list_project_files():
    response = _do_request('/repository/tree', recursive='true')
    response.raise_for_status()
    return response.json()

def _do_request(route, **params):
    if not params:
        params = None

    return requests.get(
            BASE_URL + route,
            params=params,
            headers=TOKEN_HEADER,
            proxies=PROXIES)
