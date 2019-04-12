import taskcluster


def fetch_secret(name, key):
    secrets = taskcluster.Secrets({'baseUrl': 'http://taskcluster/secrets/v1'})
    return secrets.get(name)['secret'][key]
