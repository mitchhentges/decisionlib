import datetime
from enum import Enum
import json
import os
import pprint
import re

import arrow
from git import Repo
from typing import Optional, Tuple, List, Any, Callable, Union, Dict

import sys
import taskcluster

SlugId = str


class TrustLevel(Enum):
    L1 = 1
    L3 = 3


class Trigger:
    def __init__(self, decision_task_id: SlugId, scheduler_id: str,
                 date: datetime.datetime, level: TrustLevel, owner: str, source: str):
        self.decision_task_id = decision_task_id
        self.scheduler_id = scheduler_id
        self.date = date
        self.level = level
        self.owner = owner
        self.source = source

    @staticmethod
    def from_environment():
        """Collects "DECISIONLIB_*" environment variables to create a Trigger

        Assumes that "DECISIONLIB_TASK_ID", "DECISIONLIB_TRUST_LEVEL", "DECISIONLIB_OWNER"
        and "DECISIONLIB_SOURCE" are all set as environment variables

        Returns:
            Trigger: details of the cause of this build

        """
        decision_task_id = os.environ['DECISIONLIB_DECISION_TASK_ID']
        scheduler_id = os.environ['DECISIONLIB_SCHEDULER_ID']
        date = arrow.get(os.environ['DECISIONLIB_DATE'])
        level = TrustLevel(int(os.environ['DECISIONLIB_TRUST_LEVEL']))
        owner = os.environ['DECISIONLIB_OWNER']
        source = os.environ['DECISIONLIB_SOURCE']
        return Trigger(decision_task_id, scheduler_id, date, level, owner, source)

    @staticmethod
    def from_fake(level: TrustLevel = TrustLevel.L1):
        return Trigger('<decision task id>', '<scheduler_id>', datetime.datetime.now(),
                       level, '<owner>', '<source>')


class Checkout:
    def __init__(self, ref: str, commit: str, html_url: str, alias: str):
        """Represents all information required to """

        if not ref.startswith('refs/'):
            raise ValueError('The ref provided ("{}") should follow the pattern "refs/.../...", such as '
                             '"refs/heads/master". Perhaps you want to call '
                             '"Checkout.from_branch(...)" instead?'.format(ref))

        self.ref = ref
        self.commit = commit
        self.html_url = html_url
        self.alias = alias

    @staticmethod
    def from_branch(branch: str, commit: str, html_url: str, alias: str):
        return Checkout('refs/heads/{}'.format(branch), commit, html_url, alias)

    @staticmethod
    def from_tag(tag: str, commit: str, html_url: str, alias: str):
        return Checkout('refs/tags/{}'.format(tag), commit, html_url, alias)

    @staticmethod
    def from_environment(remote: str = None):
        """Produces checkout information by checking the git repository in the current directory

        Assumes that the "origin" remote is a GitHub HTTPS URL

        Returns:
            Checkout: current source control information

        """
        repo = Repo(os.getcwd())
        remote = remote or repo.remote().url
        ref = os.environ.get('DECISIONLIB_CHECKOUT_REF', 'refs/heads/master')
        if not remote.startswith('https://github.com'):
            raise RuntimeError('Expected remote to be a GitHub repository (accessed via HTTPs)')

        if remote.endswith('.git'):
            html_url = remote[:-4]
        elif remote.endswith('/'):
            html_url = remote[:-1]
        else:
            html_url = remote

        alias = remote.split('/')[-1]
        return Checkout(str(ref), repo.head.object.hexsha, html_url, alias)

    @staticmethod
    def from_fake():
        return Checkout.from_branch('<branch>', '<commit>', '<html url>', '<product id>')


class TaskclusterQueue:
    def __init__(self, queue: taskcluster.Queue):
        self._queue = queue

    def create(self, task_id: SlugId, raw_task: dict):
        """Sends task to be run on Taskcluster

        Args:
            task_id:
            raw_task: rendered Task

        Returns: task as processed by Taskcluster

        """
        self._queue.createTask(task_id, raw_task)
        return self._queue.task(task_id)

    def get_internal(self):
        return self._queue

    @staticmethod
    def from_environment():
        """Determines Taskcluster Queue from the environment

        Uses the TASKCLUSTER_PROXY_URL from the environment to create a taskcluster.Queue

        Returns:

        """
        queue = taskcluster.Queue({'rootUrl': os.environ['TASKCLUSTER_PROXY_URL']})
        return TaskclusterQueue(queue)


def write_cot_files(full_task_graph):
    with open('task-graph.json', 'w') as f:
        json.dump(full_task_graph, f)

    # These files are needed to keep chainOfTrust happy. However, they are not needed
    # for many projects at the moment. For more details, see:
    # https://github.com/mozilla-releng/scriptworker/pull/209/files#r184180585
    for file_names in ('actions.json', 'parameters.yml'):
        with open(file_names, 'w') as f:
            json.dump({}, f)


class Scheduler:
    """Assigns IDs to tasks and batch-schedules them"""
    _tasks: List[Tuple[SlugId, 'Task']]
    _scheduled: bool

    def __init__(self):
        self._tasks = []
        self._scheduled = False

    def __del__(self):
        # When an exception has been thrown, we don't want to print this error message, since
        # the exception might've been thrown before the tasks were scheduled.
        # Fortunately, to detect this, we can use `is_finalizing()` since it is True when an
        # exception was thrown and is False here otherwise
        if not self._scheduled and not sys.is_finalizing():
            print('A Scheduler was created, but the tasks were never scheduled. Perhaps you '
                  'forgot to call ".schedule_tasks(...)" (or ".print_tasks(...)")?',
                  file=sys.stderr)

    def append(self, task: 'Task'):
        """Adds the task to the batch of tasks to be scheduled

        Args:
            task:

        Returns: task id of the added task

        """

        task_id = taskcluster.slugId()
        self._tasks.append((task_id, task))
        return task_id

    def append_all(self, tasks: List['Task']):
        for task in tasks:
            self.append(task)

    def schedule_tasks(
            self,
            queue: TaskclusterQueue,
            checkout: Checkout,
            trigger: Trigger,
            write_cot_files: Callable[[Dict], None] = write_cot_files
    ):
        """Schedules all tasks in the order that they were provided to the scheduler

        In addition to sending the tasks to the Taskcluster queue, this also creates the necessary
        Chain of Trust files.

        For example:
        ```
        queue = TaskclusterQueue.from_environment()
        trigger = Trigger.from_environment()
        checkout = Checkout.from_environment()
        scheduler.schedule_tasks(queue, checkout, trigger)
        ```

        Args:
            queue: taskcluster queue to append tasks to
            trigger: the details of the action that triggered this build
            checkout: source control information for the current revision
            write_cot_files: method of encoding Chain of Trust files (by default, writes to
                task-graph.json, actions.json and parameters.yml)

        Returns:

        """

        self._scheduled = True
        full_task_graph = {}

        for task_id, task in self._tasks:
            full_task_graph[task_id] = {
                'task': queue.create(task_id, task.render(task_id, trigger, checkout))
            }

        write_cot_files(full_task_graph)

    def fake_print_tasks(self, level: TrustLevel = TrustLevel.L1):
        """Prints the contents of each task that's been scheduled using fake context information

        Should only be used for testing, since this generates fake build information

        Args:
            level: trust level of the task

        Returns:

        """
        self._scheduled = True
        for task_id, task in self.fake_rendered_tasks(level):
            print('Task ID: {}'.format(task_id))
            pprint.pprint(task)
            print('----------')

    def fake_rendered_tasks(self, level: TrustLevel = TrustLevel.L1):
        """Prints the contents of each task that's been scheduled using fake context information

        Should only be used for testing, since this generates fake build information

        Args:
            level: trust level of the task

        Returns:

        """
        self._scheduled = True
        trigger = Trigger.from_fake(level)
        checkout = Checkout.from_fake()
        return [(task_id, task.render(task_id, trigger, checkout))
                for task_id, task in self._tasks]


class TreeherderJobKind(Enum):
    BUILD = 'build'
    TEST = 'test'
    OTHER = 'other'


class Treeherder:
    def __init__(self, job_kind: TreeherderJobKind, machine_platform: str, sheriff_tier: int,
                 symbol: str, group_symbol: str = None):
        self.symbol = symbol
        self.job_kind = job_kind
        self.sheriff_tier = sheriff_tier
        self.machine_platform = machine_platform
        self.group_symbol = group_symbol

    @staticmethod
    def from_raw(symbol: str, job_kind: Union[TreeherderJobKind, str], machine_platform: str,
                 sheriff_tier: int):
        """Parses Treeherder options from raw values

        Transforms symbol into group_symbol and job symbol according to the pattern of
        either symbol="group(job)" or just symbol="job".
        Also parses job_kind into a TreeherderJobKind if possible.

        Args:
            symbol:
            job_kind:
            machine_platform:
            sheriff_tier:

        Returns:

        """
        job_kind = TreeherderJobKind(job_kind) if type(job_kind) is str else job_kind

        pattern = re.compile(r'^(?:([\w\d\-]+)\(([\w\d\-]+)\)|([\w\d\-]+))$')
        match = pattern.match(symbol)
        if not match:
            raise ValueError('The provided symbol string does not match the structure of'
                             ' "group(symbol)" or "symbol"')

        if match.group(1) and match.group(2):
            return Treeherder(job_kind, machine_platform, sheriff_tier, match.group(2),
                              match.group(1))
        elif match.group(3):
            return Treeherder(job_kind, machine_platform, sheriff_tier, match.group(3))
        else:
            raise RuntimeError('Could not successfully extract treeherder information from symbol')


class Priority(Enum):
    HIGHEST = 'highest'
    VERY_HIGH = 'very-high'
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'
    VERY_LOW = 'very-low'
    LOWEST = 'lowest'
    NORMAL = 'normal'


class ConfigurationContext:
    def __init__(
            self,
            checkout: Checkout,
            trigger: Trigger,
    ):
        self.ref = checkout.ref
        self.commit = checkout.commit
        self.html_url = checkout.html_url
        self.alias = checkout.alias
        self.decision_task_id = trigger.decision_task_id
        self.scheduler_id = trigger.scheduler_id
        self.date = trigger.date
        self.level = trigger.level
        self.owner = trigger.owner
        self.source = trigger.source


class Task:
    """Base task builder

    For an example of how this can be extended, see "ShellTask"

    """
    _task_name: str
    _provisioner_id: str
    _payload: Any
    _worker_type: Union[Callable[[TrustLevel], str], str]
    _description: str
    _priority: Optional[Priority]
    _treeherder: Optional[Treeherder]
    _routes: List[str]
    _dependencies: List[SlugId]
    _scopes: List[str]
    _map_functions: List[Callable[['Task', ConfigurationContext], None]]
    _scheduled: bool

    def __init__(
            self,
            task_name: str,
            provisioner_id: str,
            worker_type: Union[Callable[[TrustLevel], str], str],
            payload: Any = None,
    ):
        self._task_name = task_name
        self._provisioner_id = provisioner_id
        self._payload = payload
        self._worker_type = (lambda _: worker_type) if type(worker_type) is str else worker_type
        self._description = ''
        self._routes = []
        self._dependencies = []
        self._scopes = []
        self._map_functions = []
        self._priority = None
        self._treeherder = None
        self._scheduled = False

    def __del__(self):
        # When an exception has been thrown, we don't want to print this error message, since
        # the exception might've been thrown before the ".schedule(...)" function was executed.
        # Fortunately, to detect this, we can use `is_finalizing()` since it is True when an
        # exception was thrown and is False here otherwise
        if not self._scheduled and not sys.is_finalizing():
            print('Task "{}" was created, but not scheduled. Perhaps you forgot '
                  'to call ".schedule(...)"?'.format(self._task_name), file=sys.stderr)

    def with_description(self, description: str):
        self._description = description
        return self

    def with_priority(self, priority: Union[Priority, str]):
        if type(priority) == str:
            priority = Priority(priority)
        self._priority = priority
        return self

    def with_payload(self, payload: Any):
        self._payload = payload
        return self

    def with_route(self, route: str):
        self._routes.append(route)
        return self

    def with_routes(self, routes: List[str]):
        self._routes.extend(routes)
        return self

    def with_scope(self, scope: str):
        self._scopes.append(scope)
        return self

    def with_scopes(self, scopes: List[str]):
        self._scopes.extend(scopes)
        return self

    def with_dependency(self, dependency: SlugId):
        self._dependencies.append(dependency)
        return self

    def with_dependencies(self, dependencies: List[SlugId]):
        self._dependencies.extend(dependencies)
        return self

    def with_notify_owner(self):
        """Emails the owner of the task if it fails

        Uses the trigger information (e.g.: `DECISIONLIB_OWNER` from the environment) to determine
        the owner

        Returns:

        """
        return self.map(lambda task, context: task.with_route(
            'notify.email.{}.on-failed'.format(context.owner)))

    def with_treeherder(self, symbol: str, job_kind: Union[TreeherderJobKind, str],
                        machine_platform: str, sheriff_tier: int):
        """Configures task to communicate status and results to treeherder

        Args:
            symbol: has the form "groupSymbol(taskSymbol)", or just "taskSymbol" if no group
            job_kind: changes display/treatment of the task when it completes, such as how
                "build" kinds will be red when they fail, while "test" will be orange
            machine_platform: Tasks with the same platform will be displayed on the same row
            sheriff_tier: value from 1 to 3 that controls visibility to sheriffs - 1 being "
                immediately handle this task if it fails" while a 3 is practically
                invisible to sheriffs

        Returns:

        """
        self._treeherder = Treeherder.from_raw(symbol, job_kind, machine_platform, sheriff_tier)
        return self.map(lambda task, context: task.with_route(
            'tc-treeherder.v2.{}.{}'.format(context.alias, context.commit)))

    def map(self, configuration: Callable[['Task', ConfigurationContext], None]):
        self._map_functions.append(configuration)
        return self

    def schedule(self, scheduler: Scheduler):
        """Appends task the the provided scheduler

        Args:
            scheduler:

        Returns: the task's new ID

        """
        self._scheduled = True
        return scheduler.append(self)

    def render(
            self,
            task_id: SlugId,
            trigger: Trigger,
            checkout: Checkout,
    ):
        """Produces raw Taskcluster task definition

        Should only be called by Scheduler

        Args:
            task_id: id of task
            trigger: details around the cause of this build
            checkout: source control information

        Returns:
            dict: raw taskcluster task definition

        """
        context = ConfigurationContext(checkout, trigger)
        worker_type = self._worker_type(trigger.level)
        for map_function in self._map_functions:
            map_function(self, context)

        raw_task = {
            'schedulerId': trigger.scheduler_id,
            'taskGroupId': trigger.decision_task_id,
            'provisionerId': self._provisioner_id,
            'workerType': worker_type,
            'metadata': {
                'name': self._task_name,
                'description': self._description,
                'owner': trigger.owner,
                'source': trigger.source,
            },
            'routes': self._routes,
            'dependencies': [trigger.decision_task_id] + self._dependencies,
            'scopes': self._scopes,
            'payload': self._payload or {},
            'priority': self._priority.value if self._priority else None,
            'extra': {
                'treeherder': {
                    'symbol': self._treeherder.symbol,
                    'groupSymbol': self._treeherder.group_symbol,
                    'jobKind': self._treeherder.job_kind.value,
                    'tier': self._treeherder.sheriff_tier,
                    'machine': {
                        'platform': self._treeherder.machine_platform
                    },
                } if self._treeherder else None
            },
            'created': taskcluster.stringDate(datetime.datetime.utcnow()),
            'deadline': taskcluster.stringDate(taskcluster.fromNow('1 day')),
        }

        # Removes null values from JSON to avoid situations like: '{ ... "priority": null}'
        if not raw_task['priority']:
            del raw_task['priority']

        if not raw_task['extra']['treeherder']:
            del raw_task['extra']['treeherder']

        if not raw_task['extra']:
            del raw_task['extra']

        return raw_task


class ArtifactType(Enum):
    FILE = 'file'
    DIRECTORY = 'directory'


class Artifact:
    def __init__(self, taskcluster_path: str, relative_fs_path: str, type: ArtifactType):
        """File or directory on worker that's uploaded to Taskcluster

        Args:
            taskcluster_path: path on Taskcluster, such as "public/target.apk"
            relative_fs_path: path to the artifact on the FS relative to the checkout directory
            type: file or directory
        """
        self.taskcluster_path = taskcluster_path
        self.relative_fs_path = relative_fs_path
        self.type = type


class AndroidArtifact(Artifact):
    taskcluster_path: str
    outputs_apk_path: str
    type: ArtifactType

    def __init__(self, taskcluster_path: str, outputs_apk_path: str):
        """

        Args:
            taskcluster_path: path of artifact on Taskcluster
            outputs_apk_path: path to apk within gradle's "outputs/apks/
        """
        super().__init__(
            taskcluster_path,
            'app/build/outputs/apk/{}'.format(outputs_apk_path),
            ArtifactType.FILE
        )


class ShellTask(Task):
    """Represents a task that runs within a docker image and is configured with a bash script

    Note that if you're using a python 2 docker image and use decisionlib (e.g.: to fetch secrets,)
    then you should call "with_install_python_3()", otherwise installing decisionlib will fail

    """
    _docker_image: str
    _scripts: List[str]
    _artifacts: List[Artifact]
    _file_secrets: List[Tuple[str, str, str]]
    _install_python_3: bool

    def __init__(
            self,
            task_name: str,
            provisioner_id: str,
            worker_type: Union[Callable[[TrustLevel], str], str],
            docker_image: str,
            script: str = None,
    ):
        """Creates shell task

        Args:
            task_name:
            provisioner_id:
            worker_type:
            docker_image:
            script: Shell script to run with bash. Additional scripts can be appended using
                "with_script"
        """
        super().__init__(task_name, provisioner_id, worker_type)
        self._docker_image = docker_image
        self._scripts = [script] if script else []
        self._artifacts = []
        self._file_secrets = []
        self._install_python_3 = False

    def with_artifact(self, artifact: Artifact):
        self._artifacts.append(artifact)
        return self

    def with_artifacts(self, artifacts: List[Artifact]):
        self._artifacts.extend(artifacts)
        return self

    def with_secret(self, secret: str):
        self.with_scope('secrets:get:{}'.format(secret))
        return self

    def with_file_secret(self, secret, key, target_file):
        self._file_secrets.append((secret, key, target_file))
        return self.with_secret(secret)

    def with_install_python_3(self):
        """Installs python3 with apt and sets it as the default for python and pip

        Returns:

        """
        self._install_python_3 = True
        return self

    def with_script(self, script):
        """Appends a script to be run as part of this task

        Args:
            script:

        Returns:

        """
        self._scripts.append(script)
        return self

    def render(
            self,
            task_id: SlugId,
            trigger: Trigger,
            checkout: Checkout,
    ):
        if self._file_secrets:
            fetch_file_secrets_commands = ['pip install decisionlib-mhentges'] + [
                'decisionlib get-secret {} {} > {}'.format(secret, key, target_file)
                for secret, key, target_file in self._file_secrets
            ]
        else:
            fetch_file_secrets_commands = []

        def configuration(task: Task, context: ConfigurationContext):
            script = '\n'.join([
                """
                export TERM=dumb
                git init /tmp/build
                cd /tmp/build
                git fetch {url} {ref}
                git config advice.detachedHead false
                git checkout FETCH_HEAD
                """.format(url=context.html_url, ref=context.ref),
                """
                apt install -y python3-pip
                shopt -s expand_aliases
                alias pip=pip3
                alias python=python3
                """ if self._install_python_3 else '',
                *fetch_file_secrets_commands,
                *self._scripts
            ])
            script = re.sub('\n\\s+', '\n', script).strip()  # de-indent

            task.with_payload({
                'maxRunTime': 86400,
                'features': {
                    'chainOfTrust': True if self._artifacts else False,
                    'taskclusterProxy': True if self._file_secrets else False,
                },
                'image': self._docker_image,
                'command': ['/bin/bash', '--login', '-cxe', script],
                'artifacts': {
                    artifact.taskcluster_path: {
                        'type': artifact.type.value,
                        'path': '/tmp/build/{}'.format(artifact.relative_fs_path),
                    }
                    for artifact in self._artifacts
                }
            })

        self.map(configuration)
        return super().render(task_id, trigger, checkout)


def mobile_shell_task(
        task_name: str,
        docker_image: str,
        script: str,
        worker_type_suffix: str
):
    """Builds task that runs as shell commands in a docker container

    Clones the project repository in the docker image and installs decision_lib. The working
    directory is within the cloned repository

    Args:
        task_name: name of task
        docker_image: docker image
        script: commands to run within the container
        worker_type_suffix: the ending to the worker type, such as the "ref-browser"
            in "mobile-1-b-ref-browser"

    Returns:
        ShellTask: shell task builder
    """

    def decide_worker_type(level: TrustLevel):
        return 'mobile-{}-b-{}'.format(level.value, worker_type_suffix)

    return ShellTask(
        task_name,
        'aws-provisioner-v1',
        decide_worker_type,
        docker_image,
        script,
    )


class SigningType(Enum):
    DEP = 'dep'
    RELEASE = 'release'


def mobile_sign_task(
        task_name: str,
        signing_format: str,
        signing_type: Union[str, SigningType],
        *upstream_artifacts: Tuple[SlugId, List[str]],
):
    """Builds task that runs within "mobile-signing-(dep-)v1" workers

    Note: signing tasks automatically expose artifacts: for each incoming APK, they expose the
    signed version under the same taskcluster path.

    So, task artifacts will look similar to:
    build task => [target.arm.apk, target.aarch64.apk] (both unsigned)
    sign task => [target.arm.apk, target.aarch64.apk] (both signed)

    Args:
        task_name: name of task
        signing_format: signing format, such as "autograph_apk"
        signing_type: what type of signing key should be used. Can be defined with strings
            ("dep"/"release") or the SigningType enum itself
        upstream_artifacts: task id + apk paths combinations that this task will sign.
            For example: (assemble_task_id, [artifact_1_path, artifact_2_path)

    Returns:
        Task: task builder
    """

    if type(signing_type) == str:
        signing_type = SigningType(signing_type)

    payload = {
        'upstreamArtifacts': [{
            'paths': apk_paths,
            'formats': [signing_format],
            'taskId': assemble_task_id,
            'taskType': 'build'
        } for assemble_task_id, apk_paths in upstream_artifacts]
    }

    def decide_worker_type(level: TrustLevel):
        if level == TrustLevel.L1 and signing_type == SigningType.RELEASE:
            raise RuntimeError('Cannot use RELEASE signing type with a trust level of 1')

        return 'mobile-signing-dep-v1' if signing_type == SigningType.DEP else 'mobile-signing-v1'

    return Task(task_name, 'scriptworker-prov-v1', decide_worker_type, payload) \
        .with_dependencies([assemble_task_id for assemble_task_id, _ in upstream_artifacts]) \
        .map(
        lambda task, context: task.with_scopes([
            'project:mobile:{}:releng:signing:format:{}'.format(
                context.alias, signing_format),
            'project:mobile:{}:releng:signing:cert:{}-signing'.format(
                context.alias, signing_type.value),
        ]))


def mobile_google_play_task(
        task_name: str,
        track: str,
        upstream_artifacts: List[Tuple[SlugId, List[str]]],
):
    """Builds task that runs within "mobile-pushapk-(dep-)v1" workers

    Args:
        task_name: name of task
        track: Google Play track
        upstream_artifacts: task id and path to apks that this task will sign. For example:
            (<assemble_task_id>, [<artifact_1_path>, <artifact_2_path>])

    Returns:
        Task: task builder
    """
    payload = {
        'commit': True,
        'google_play_track': track,
        'upstreamArtifacts': [{
            'paths': apk_paths,
            'taskId': signing_task_id,
            'taskType': 'signing'
        } for signing_task_id, apk_paths in upstream_artifacts]
    }

    def decide_worker_type(level: TrustLevel):
        return 'mobile-pushapk-dep-v1' if level == TrustLevel.L1 else 'mobile-pushapk-v1'

    return Task(task_name, 'scriptworker-prov-v1', decide_worker_type, payload) \
        .with_dependencies([signing_task_id for signing_task_id, _ in upstream_artifacts]) \
        .map(
        lambda task, context: task.with_scopes([
            'project:mobile:{alias}:releng:googleplay:product:{alias}{type}'.format(
                alias=context.alias,
                type=':dep' if context.level == TrustLevel.L1 else ''
            )
        ]))


class TaskclusterArtifact:
    """Represents direct URL to artifact on Taskcluster"""

    def __init__(self, task_id: str, path: str):
        self.task_id = task_id
        self.path = path

    def url(self):
        return 'https://queue.taskcluster.net/v1/task/{}/artifacts/{}' \
            .format(self.task_id, self.path)


def mobile_raptor_task(
        task_name: str,
        test_name: str,
        signed_apk: Tuple[SlugId, str],
        mozharness_task_id: str,
        is_arm: bool,
        raptor_app_id: str,
        package_name: str,
        activity_class_name: str,
        gecko_revision: str,
        test_linux_args: List[str] = ()
):
    """Builds raptor performance-testing task

    Args:
        task_name: name of task
        test_name: name of raptor test
        signed_apk: id of signing task and path to apk
        mozharness_task_id: id of mozharness task
        is_arm: true if signed apk uses the ARM abi
        raptor_app_id: raptor-specific app identifier
        package_name: package name
        activity_class_name: activity to test
        gecko_revision: gecko revision
        test_linux_args: additional arguments to provide to "test-linux.sh"

    Returns:
        Task: task builder
    """
    signed_apk = TaskclusterArtifact(signed_apk[0], signed_apk[1])
    worker_type = 'gecko-t-ap-perf-g5' if is_arm else 'gecko-t-ap-perf-p2'
    artifacts = [{
        'path': '/builds/worker/{}'.format(worker_path),
        'type': 'directory',
        'name': 'public/{}/'.format(public_folder),
    } for worker_path, public_folder in (
        ('artifacts', 'test'),
        ('workspace/build/logs', 'logs'),
        ('workspace/build/blobber_upload_dir', 'test_info')
    )]

    payload = {
        'artifacts': artifacts,
        'command': [
            './test-linux.sh',
            '--installer-url={}'.format(signed_apk.url()),
            '--test-packages-url={}'.format(TaskclusterArtifact(
                mozharness_task_id, 'public/build/target.test_packages.json').url()),
            '--test={}'.format(test_name),
            '--app={}'.format(raptor_app_id),
            '--binary={}'.format(package_name),
            '--activity={}'.format(activity_class_name),
            '--download-symbols=ondemand',
        ] + list(test_linux_args),
        'env': {
            'XPCOM_DEBUG_BREAK': 'warn',
            'MOZ_NO_REMOTE': '1',
            'MOZ_HIDE_RESULTS_TABLE': '1',
            'TAKSLUCSTER_WORKER_TYPE': 'proj-autophone/{}'.format(worker_type),
            'MOZHARNESS_URL': TaskclusterArtifact(
                mozharness_task_id, 'public/build/mozharness.zip').url(),
            'MOZHARNESS_SCRIPT': 'raptor_script.py',
            'NEED_XVFB': 'false',
            'WORKING_DIR': '/builds/worker',
            'WORKSPACE': '/builds/worker/workspace',
            'MOZ_NODE_PATH': '/usr/local/bin/node',
            'NO_FAIL_ON_TEST_ERRORS': '1',
            'MOZHARNESS_CONFIG': 'raptor/android_hw_config.py',
            'MOZ_AUTOMATION': '1',
            'MOZILLA_BUILD_URL': signed_apk.url()
        },
        'context': 'https://hg.mozilla.org/mozilla-central/raw-file/{}/'
                   'taskcluster/scripts/tester/test-linux.sh'.format(gecko_revision),
    }

    return Task(task_name, 'proj-autophone', worker_type) \
        .with_dependency(signed_apk.task_id) \
        .with_payload(payload)
