from .models import Agent, Job, Installed_Job, Instance, Watch
from django.http import JsonResponse
from django.core.exceptions import ObjectDoesNotExist
import json
import socket
import ConfigParser
from django.utils import timezone


def add_agent(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    try:
        agent = Agent(address = data['address'], username = data['username'],
                      password = data['password'], collector = data['collector'])
    except:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    if 'name' in data:
        agent.name = data['name']
    agent.reachable = "Installing ..."
    agent.update_reachable = timezone.now()
    agent.status = "Installing ..." 
    agent.update_status = timezone.now()
    agent.save()
    response_data = {}
    cmd = "add_agent " + agent.address
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 1113))
    s.send(cmd)
    r = s.recv(1024)
    s.close()
    response_data['msg'] = r
    if r.split()[0] == 'KO':
        agent.delete()
        return JsonResponse(data=response_data, status=404)
    agent.reachable = "Agent reachable"
    agent.update_reachable = timezone.now()
    agent.status = "Available"
    agent.update_status = timezone.now()
    agent.save()
    return JsonResponse(data=response_data, status=200)


def del_agent(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    try:
        ip_address = data['address']
    except:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    try:
        agent = Agent.objects.get(pk=ip_address)
    except ObjectDoesNotExist:
        response_data = {'msg': "This Agent isn't in the database", 'address':
                         ip_address}
        return JsonResponse(data=response_data, status=404)
    response_data = {}
    cmd = "del_agent " + " " + agent.address
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 1113))
    s.send(cmd)
    r = s.recv(1024)
    s.close()
    response_data['msg'] = r
    if r.split()[0] == 'OK':
        agent.delete()
        return JsonResponse(data=response_data, status=200)
    return JsonResponse(data=response_data, status=404)


def list_agents(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    agents = Agent.objects.all()
    update = False
    response_data = {'errors': list()}
    if 'update' in data:
        update = data['update']
    if update:
        for agent in agents:
            if agent.reachable == 'Agent reachable' and agent.update_status < agent.update_reachable:
                cmd = "update_agent " + agent.address
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect(('localhost', 1113))
                s.send(cmd)
                r = s.recv(1024)
                s.close()
                return_msg = r.split()
                if return_msg[0] == 'KO':
                    response_data['errors'].append({'agent_ip': agent.address,
                                                    'error': ' '.join(return_msg[1:])})
    response_data['agents'] = list()
    for agent in agents:
        agent.refresh_from_db()
        agent_json = {'address': agent.address, 'status': agent.status,
                      'update_status': agent.update_status, 'name': agent.name}
        response_data['agents'].append(agent_json)
    return JsonResponse(response_data, status=200)


def add_job(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    try:
        job_name = data['name']
        job_path = data['path']
    except:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    conffile = job_path + "/templates/" + job_name + '.cfg'
    Config = ConfigParser.ConfigParser()
    Config.read(conffile)
    job_args = Config.get(job_name, 'required')
    optional_args = bool(Config.get(job_name, 'optional'))
    nb_args = len(job_args.split())
    job = Job(name = job_name, path = job_path, nb_args = nb_args,
              optional_args = optional_args)
    job.save()
    response_data = {'msg': "OK"}
    return JsonResponse(data=response_data, status=200)


def del_job(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    try:
        job_name = data['name']
    except:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    try:
        job = Job.objects.get(pk=job_name)
    except ObjectDoesNotExist:
        response_data = {'msg': "This Job isn't in the database", 'job_name':
                         job_name}
        return JsonResponse(data=response_data, status=404)
    job.delete()
    response_data = {'msg': "OK"}
    return JsonResponse(data=response_data, status=200)


def list_jobs(request):
    if request.method != 'GET':
        response_data = {'msg': "Only GET method are accepted"}
        return JsonResponse(data=response_data, status=404)
    jobs = Job.objects.all()
    response_data = {}
    response_data['jobs'] = list()
    for job in jobs:
        response_data['jobs'].append(job.name)
    return JsonResponse(response_data, status=200)


def install_job(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    if 'addresses' not in data and 'names' not in data:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    agents = []
    jobs = []
    try:
        for i in range(len(data['addresses'])):
            agents.append(Agent.objects.get(pk=data['addresses'][i]))
    except ObjectDoesNotExist:
        response_data = {'msg': "At least one of the Agents isn't in the"
                         " database", 'address': data['addresses'][i]}
        return JsonResponse(data=response_data, status=404)
    try:
        for i in range(len(data['names'])):
            jobs.append(Job.objects.get(pk=data['names'][i]))
    except ObjectDoesNotExist:
        response_data = {'msg': "At least one of the Jobs isn't in the"
                         " database", 'job_name': data['names'][i]}
        return JsonResponse(data=response_data, status=404)
    success = True
    for i in range(len(agents)):
        agent = agents[i]
        for l in range(len(jobs)):
            job = jobs[l]
            cmd = "install_job " + agent.address + " \"" + job.name + "\""
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(('localhost', 1113))
            s.send(cmd)
            r = s.recv(1024)
            s.close()
            if r.split()[0] == 'OK':
                installed_job = Installed_Job(agent=agent, job=job)
                installed_job.set_name()
                installed_job.update_status = timezone.now()
                installed_job.save()
            if success:
                success = r.split()[0] == 'OK'
    if success:
        response_data = {'msg': "OK"}
        return JsonResponse(data=response_data, status=200)
    else:
        response_data = {'msg': "At least one of the installation have failed"}
        return JsonResponse(data=response_data, status=404)


def uninstall_job(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    if 'addresses' not in data and 'names' not in data:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    agents = []
    jobs = []
    try:
        for i in range(len(data['addresses'])):
            agents.append(Agent.objects.get(pk=data['addresses'][i]))
    except ObjectDoesNotExist:
        response_data = {'msg': "At least one of the Agents isn't in the"
                         " database", 'address': data['addresses'][i]}
        return JsonResponse(data=response_data, status=404)
    try:
        for i in range(len(data['names'])):
            jobs.append(Job.objects.get(pk=data['names'][i]))
    except ObjectDoesNotExist:
        response_data = {'msg': "At least one of the Jobs isn't in the"
                         " database", 'job_name': data['names'][i]}
        return JsonResponse(data=response_data, status=404)
    success = True
    error_msg = []
    for i in range(len(agents)):
        agent = agents[i]
        for l in range(len(jobs)):
            job = jobs[l]
            installed_job_name = job.name + " on " + agent.address
            try:
                installed_job = Installed_Job.objects.get(pk=installed_job_name)
            except ObjectDoesNotExist:
                error_msg.append({'error': "The Installed_Job isn't in the "
                                  "database", 'job_name': installed_job_name})
                continue
            cmd = "uninstall_job " + agent.address + " \"" + job.name + "\""
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(('localhost', 1113))
            s.send(cmd)
            r = s.recv(1024)
            s.close()
            if r.split()[0] == 'OK':
                installed_job.delete()
            else:
                success = False
                error_msg.append("The uninstall of " + installed_job_name +
                                 " wen't wrong\n")
    if success:
        if len(error_msg) != 0:
            msg = "OK but\n"
            for i in range(len(error_msg)):
                msg += error_msg[i]
        else:
            msg = "OK"
        response_data = {'msg': msg}
        return JsonResponse(data=response_data, status=200)
    else:
        response_data = {'msg': error_msg}
        return JsonResponse(data=response_data, status=404)


def list_installed_jobs(request, ip_address):
    if request.method != 'GET':
        response_data = {'msg': "Only GET method are accepted"}
        return JsonResponse(data=response_data, status=404)
    try:
        agent = Agent.objects.get(pk=ip_address)
    except ObjectDoesNotExist:
        response_data = {'msg': "This Agent isn't in the database", 'address':
                         ip_address}
        return JsonResponse(data=response_data, status=404)
    response_data = {}
    response_data['agent'] = agent.address
    response_data['installed_jobs'] = list()
    try:
        installed_jobs = agent.installed_job_set
    except (KeyError, Installed_Job.DoesNotExist):
        return JsonResponse(response_data, status=200)
    else:
        for job in installed_jobs.iterator():
            job_json = {'name': job.job.name, 'update_status': job.update_status}
            response_data['installed_jobs'].append(job_json)
        return JsonResponse(response_data, status=200)


def start_instance(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    try:
        agent_ip = data['agent_ip']
        job_name = data['job_name']
        instance_args = data['args']
    except:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    name = job_name + " on " + agent_ip
    try:
        installed_job = Installed_Job.objects.get(pk=name)
    except ObjectDoesNotExist:
        response_data = {'msg': "This Installed_Job isn't in the database",
                         'job_name': name}
        return JsonResponse(data=response_data, status=404)
    if 'date' in data:
        date = data['date']
        date_interval = 'date'
    elif 'interval' in data:
        interval = data['interval']
        date_interval = 'interval'
    else:
        date = 'now'
        date_interval = 'date'
    instance = Instance(job=installed_job)
    if len(instance_args) != 0:
        instance.args = " ".join(instance_args)
    if not instance.check_args():
        response_data = {'msg': "Arguments given don't match with arguments "
                         "needed"}
        return JsonResponse(data=response_data, status=404)
    instance.status = "starting ..."
    instance.update_status = timezone.now()
    instance.save()
    instance_id = str(instance.id)
    cmd = "start_instance "
    if date_interval == 'date':
        cmd += "date " + str(date)
    else:
        cmd += "interval " + str(interval)
    cmd += " " + instance_id
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 1113))
    s.send(cmd)
    r = s.recv(1024)
    s.close()
    response_data = {'msg': r}
    if r.split()[0] == 'OK':
        instance.status = "started"
        instance.update_status = timezone.now()
        instance.save()
        response_data['instance_id'] = instance_id
        return JsonResponse(data=response_data, status=200)
    else:
        instance.delete()
        return JsonResponse(data=response_data, status=404)


def stop_instance(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    try:
        instance_id = data['instance_id']
    except:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    try:
        instance = Instance.objects.get(pk=instance_id)
    except ObjectDoesNotExist:
        response_data = {'msg': "This Instance isn't in the database",
                         'instance_id': instance_id}
        return JsonResponse(data=response_data, status=404)
    if 'date' in data:
        date = data['date']
    else:
        date = "now"
    cmd = "stop_instance " + date + " " + instance_id
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 1113))
    s.send(cmd)
    r = s.recv(1024)
    s.close()
    response_data = {'msg': r}
    if r.split()[0] == 'OK':
        instance.delete()
        return JsonResponse(data=response_data, status=200)
    else:
        return JsonResponse(data=response_data, status=404)


def restart_instance(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    try:
        instance_id = data['instance_id']
        instance_args = data['args']
    except:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    try:
        instance = Instance.objects.get(pk=instance_id)
    except ObjectDoesNotExist:
        response_data = {'msg': "This Instance isn't in the database",
                         'instance_id': instance_id}
        return JsonResponse(data=response_data, status=404)
    if 'date' in data:
        date = data['date']
        date_interval = 'date'
    elif 'interval' in data:
        interval = data['interval']
        date_interval = 'interval'
    else:
        date = 'now'
        date_interval = 'date'
    if len(instance_args) != 0:
        instance.args = " ".join(instance_args)
        if not instance.check_args():
            response_data = {'msg': "Arguments given don't match with arguments "
                             "needed"}
            return JsonResponse(data=response_data, status=404)
        instance.save()
    instance_id = str(instance.id)
    cmd = "restart_instance "
    if date_interval == 'date':
        cmd += "date " + date
    else:
        cmd += "interval " + interval
    cmd += " " + instance_id
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 1113))
    s.send(cmd)
    r = s.recv(1024)
    s.close()
    response_data = {'msg': r}
    if r.split()[0] == 'OK':
        return JsonResponse(data=response_data, status=200)
    else:
        # TODO delete or keep the instance in the database ?
        return JsonResponse(data=response_data, status=404)


def status_agents(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    if 'addresses' not in data:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    agents_ip = data['addresses']
    cmd = "status_agents " + ' '.join(agents_ip)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 1113))
    s.send(cmd)
    r = s.recv(1024)
    s.close()
    response = r.split()
    if response[0] == 'OK':
        response_data = {'msg': r}
        return JsonResponse(data=response_data, status=200)
    else:
        response_data = {'msg': "At least one of the Agents isn't in the"
                         "database", 'addresses': response}
        return JsonResponse(data=response_data, status=404)

def status_jobs(request):
    pass


def status_instance(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    try:
        instance_id = data['instance_id']
    except:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    try:
        instance = Instance.objects.get(pk=instance_id)
        installed_job = instance.job
    except ObjectDoesNotExist:
        if 'agent_ip' not in data or 'job_name' not in data:
            response_data = {'msg': "POST data malformed"}
            return JsonResponse(data=response_data, status=404)
        else:
            agent_ip = data['agent_ip']
            job_name = data['job_name']
            try:
                agent = Agent.objects.get(pk=agent_ip)
            except ObjectDoesNotExist:
                response_data = {'msg': "This Agent isn't in the database", 'address':
                                 agent_ip}
                return JsonResponse(data=response_data, status=404)
            try:
                job = Job.objects.get(pk=job_name)
            except ObjectDoesNotExist:
                response_data = {'msg': "This Job isn't in the database", 'job_name':
                                 job_name}
                return JsonResponse(data=response_data, status=404)
            name = job.name + " on " + agent.address
            try:
                installed_job = Installed_Job.objects.get(pk=name)
            except ObjectDoesNotExist:
                response_data = {'msg': "This Installed_Job isn't in the database",
                                 'job_name': name}
                return JsonResponse(data=response_data, status=404)
    if 'date' in data:
        try:
            Watch.objects.get(pk=instance_id)
            response_data = {'msg': "A Watch already exist in the database"}
            return JsonResponse(data=response_data, status=404)
        except ObjectDoesNotExist:
            watch = Watch(job=installed_job, instance_id=instance_id,
                          interval=0) 
        watch_type = 'date'
        cmd_type = "date " + str(data['date']) + " "
    elif 'interval' in data:
        try:
            watch = Watch.objects.get(pk=instance_id)
        except ObjectDoesNotExist:
            watch = Watch(job=installed_job, instance_id=instance_id)
        watch_type = 'interval'
        interval = int(data['interval'])
        watch.interval = interval
        cmd_type = "interval " + str(interval) + " "
    elif 'stop' in data:
        try:
            watch = Watch.objects.get(pk=instance_id)
        except ObjectDoesNotExist:
            watch = Watch(job=installed_job, instance_id=instance_id,
                          interval=0)
        watch_type = 'stop'
        cmd_type = "stop " + str(data['stop']) + " "
    else:
        try:
            Watch.objects.get(pk=instance_id)
            response_data = {'msg': "A Watch already exist in the database"}
            return JsonResponse(data=response_data, status=404)
        except ObjectDoesNotExist:
            watch = Watch(job=installed_job, instance_id=instance_id,
                          interval=0)
        watch_type = 'date'
        cmd_type = "date now "
    watch.save()
    cmd = "status_instance " + cmd_type +  str(instance_id)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 1113))
    s.send(cmd)
    r = s.recv(1024)
    s.close()
    response_data = {'msg': r}
    if r.split()[0] == 'OK':
        if watch_type != 'interval':
            watch.delete()
        return JsonResponse(data=response_data, status=200)
    else:
        watch.delete()
        return JsonResponse(data=response_data, status=404)


def list_instances(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    try:
        agents_ip = data['agents_ip']
    except:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    if 'update' in data:
        update = data['update']
    else:
        update = False
    response_data = {}
    response_data['instances'] = list()
    if len(agents_ip) == 0:
        agents = Agent.objects.all()
        for agent in agents:
            agents_ip.append(agent.address)
    for ip_address in agents_ip:
        try:
            try:
                agent = Agent.objects.get(pk=ip_address)
            except ObjectDoesNotExist:
                raise ObjectDoesNotExist
            instances_for_agent = {'address': ip_address}
            instances_for_agent['installed_job'] = list()
            for installed_job in agent.installed_job_set.get_queryset().iterator():
                installed_job_json = {'job_name': installed_job.job.name}
                installed_job_json['instances'] = list()
                for instance in installed_job.instance_set.get_queryset().iterator():
                    if update:
                        # TODO: Connect to the collector and get the status of the instance
                        pass
                    instance_json = {'id': instance.id, 'arguments': instance.args,
                                     'update_status': instance.update_status, 'status':
                                     instance.status}
                    installed_job_json['instances'].append(instance_json)
                instances_for_agent['installed_job'].append(installed_job_json)
        except ObjectDoesNotExist:
            response_data = {'msg': "At least one of the Agents isn't in the"
                             " database", 'address': ip_address}
            return JsonResponse(data=response_data, status=404)
        response_data['instances'].append(instances_for_agent)
    return JsonResponse(response_data, status=200)


