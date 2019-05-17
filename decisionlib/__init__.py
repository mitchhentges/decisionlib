import argparse
from typing import Optional

from decisionlib.schedule import schedule, schedule_hook
from decisionlib.shell import fetch_secret


def to_ref(ref: Optional[str], branch: Optional[str], tag: Optional[str]):
    if ref:
        if not ref.startswith('refs'):
            raise ValueError('The ref provided ("{}") should follow the pattern "refs/.../...", such as '
                             '"refs/heads/master". Perhaps you want to use --tag or --branch instead of '
                             '--ref?'.format(ref))
        return ref
    elif tag:
        return 'refs/tags/{}'.format(tag)
    else:
        return 'refs/heads/{}'.format(branch or 'master')


def main():
    parser = argparse.ArgumentParser(
        description='Schedule tasks or request secrets from taskcluster'
    )
    command_subparser = parser.add_subparsers(dest='command')
    command_subparser.required = True

    schedule_parser = command_subparser.add_parser('schedule')
    schedule_parser.add_argument('--revision')
    ref_group = schedule_parser.add_mutually_exclusive_group()
    ref_group.add_argument('--ref')
    ref_group.add_argument('--tag')
    ref_group.add_argument('--branch')
    schedule_parser.add_argument('decision_file')
    schedule_parser.add_argument('repository')
    schedule_parser.add_argument('decision_file_arguments', nargs=argparse.REMAINDER)

    hook_parser = command_subparser.add_parser('schedule-hook')
    hook_parser.add_argument('task_id')
    hook_parser.add_argument('repository')
    hook_parser.add_argument('--revision')
    hook_parser.add_argument('--dry-run', action='store_true')
    ref_group = hook_parser.add_mutually_exclusive_group()
    ref_group.add_argument('--ref')
    ref_group.add_argument('--tag')
    ref_group.add_argument('--branch')

    secret_parser = command_subparser.add_parser('get-secret')
    secret_parser.add_argument('secret', help='name of the secret')
    secret_parser.add_argument('key', help='key of the secret')

    result = parser.parse_args()
    if result.command == 'schedule':
        ref = to_ref(result.ref, result.branch, result.tag)
        schedule(result.decision_file, result.repository, ref, result.revision, result.decision_file_arguments)
    if result.command == 'schedule-hook':
        ref = to_ref(result.ref, result.branch, result.tag)
        schedule_hook(result.task_id, result.repository, ref, result.revision, result.dry_run)
    if result.command == 'get-secret':
        print(fetch_secret(result.secret, result.key))


if __name__ == '__main__':
    main()
