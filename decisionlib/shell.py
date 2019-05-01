import os

import taskcluster


def fetch_secret(name, key):
    secrets = taskcluster.Secrets({'rootUrl': os.environ['TASKCLUSTER_PROXY_URL']})
    return secrets.get(name)['secret'][key]
