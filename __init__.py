import argparse

from decisionlib.hook import schedule_hook
from decisionlib.shell import fetch_secret


def main():
    parser = argparse.ArgumentParser(
        description='Schedule tasks or request secrets from taskcluster'
    )
    command_subparser = parser.add_subparsers(dest='command')
    command_subparser.required = True

    hook_parser = command_subparser.add_parser('schedule-hook')
    hook_parser.add_argument('task_id')
    hook_parser.add_argument('repository')
    hook_parser.add_argument('--branch', default='master')
    hook_parser.add_argument('--revision')
    hook_parser.add_argument('--dry-run', action='store_true')

    secret_parser = command_subparser.add_parser('get-secret')
    secret_parser.add_argument('secret', help='name of the secret')
    secret_parser.add_argument('key', help='key of the secret')

    result = parser.parse_args()
    if result.command == 'schedule-hook':
        schedule_hook(result.task_id, result.repository, result.branch, result.revision,
                      result.dry_run)
    if result.command == 'get-secret':
        print(fetch_secret(result.secret, result.key))


if __name__ == '__main__':
    main()
