from decisionlib.decisionlib.decisionlib import *


def main():
    scheduler = Scheduler()
    mobile_shell_task('assemble', 'mozillamobile/fenix:1.0', './gradlew assembleRelease', 'ref-browser') \
        .with_treeherder('groupBonk(S)', 'other', '<machine platform>', 1) \
        .schedule(scheduler)

    scheduler.print_tasks()


if __name__ == '__main__':
    main()
