import datetime
import os
import subprocess
import sys
from typing import Optional

import jsone
import slugid
import taskcluster
import yaml


def clone_and_cd(html_url, branch_or_tag):
    subprocess.check_call(
        # "--branch" takes both branch names and tags, surprisingly
        'git clone {} --single-branch --branch {} --depth 1'.format(html_url, branch_or_tag),
        shell=True
    )
    repository_directory_name = html_url.split('/')[-1]
    os.chdir(repository_directory_name)


def checkout_revision(revision):
    subprocess.check_call('git checkout {}'.format(revision), shell=True)


def load_revision():
    return subprocess.check_output(
        'git rev-parse --verify HEAD',
        encoding='utf=8',
        shell=True,
    ).strip()


def schedule(decision_file: str, html_url: str, ref: str, revision: Optional[str], decision_file_arguments: [str]):
    if not html_url.startswith('https://github.com/'):
        raise ValueError('expected repository to be a GitHub repository (accessed via HTTPs)')

    html_url = html_url[:-4] if html_url.endswith('.git') else html_url
    html_url = html_url[:-1] if html_url.endswith('/') else html_url

    branch_or_tag = ref.split('/')[-1]
    clone_and_cd(html_url, branch_or_tag)
    if revision:
        checkout_revision(revision)

    subprocess.check_call('{} {} {}'.format(sys.executable, decision_file, ' '.join(decision_file_arguments)),
                          shell=True)


def schedule_hook(task_id: str, html_url: str, ref: str, revision: str, dry_run: bool):
    if not html_url.startswith('https://github.com/'):
        raise ValueError('expected repository to be a GitHub repository (accessed via HTTPs)')

    html_url = html_url[:-4] if html_url.endswith('.git') else html_url
    html_url = html_url[:-1] if html_url.endswith('/') else html_url

    repository_full_name = html_url[len('https://github.com/'):]
    branch_or_tag = ref.split('/')[-1]
    clone_and_cd(html_url, branch_or_tag)
    if revision:
        checkout_revision(revision)
    else:
        revision = load_revision()

    with open('.taskcluster.yml', 'rb') as f:
        taskcluster_yml = yaml.safe_load(f)

    # provide a similar JSON-e context to what taskcluster-github provides
    slugids = {}

    def as_slugid(name):
        if name not in slugids:
            slugids[name] = slugid.nice()
        return slugids[name]

    context = {
        'tasks_for': 'cron',
        'cron': {
            'task_id': task_id,
        },
        'now': datetime.datetime.utcnow().isoformat()[:23] + 'Z',
        'as_slugid': as_slugid,
        'event': {
            'repository': {
                'html_url': html_url,
                'full_name': repository_full_name,
            },
            'release': {
                'tag_name': revision,
                'target_commitish': ref,
            },
            'sender': {
                'login': 'TaskclusterHook',
            },
        },
    }

    rendered = jsone.render(taskcluster_yml, context)
    if len(rendered['tasks']) != 1:
        raise RuntimeError('Expected .taskcluster.yml in {} to only produce one cron task'
                           .format(html_url))

    task = rendered['tasks'][0]
    task_id = task.pop('taskId')

    print('Decision task ID: {}'.format(task_id))
    if not dry_run:
        queue = taskcluster.Queue({'rootUrl': os.environ['TASKCLUSTER_PROXY_URL']})
        queue.createTask(task_id, task)
    else:
        print(task)
