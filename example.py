from decisionlib.decisionlib import Scheduler, mobile_shell_task, AndroidArtifact, mobile_sign_task, \
    SigningType, Trigger, Checkout, TaskclusterQueue


def main():
    scheduler = Scheduler()
    assemble_task_id = mobile_shell_task('assemble', 'mozillamobile/fenix:1.0',
                                         './gradlew assembleRelease', 'ref-browser') \
        .with_artifact(AndroidArtifact('public/target.apk', 'release/app-release.apk')) \
        .with_treeherder('build', 'android-all', 1, 'B') \
        .with_notify_owner() \
        .schedule(scheduler)

    mobile_sign_task('sign', 'autograph_apk', SigningType.DEP,
                     [(assemble_task_id, ['public/target.apk'])]) \
        .with_treeherder('S', 'other', 'android-all', 1) \
        .with_notify_owner() \
        .with_route('index.project.mobile.fenix.release.latest') \
        .schedule(scheduler)

    queue = TaskclusterQueue.from_environment()
    trigger = Trigger.from_environment()
    checkout = Checkout.from_environment()
    scheduler.schedule_tasks(queue, checkout, trigger)


if __name__ == '__main__':
    main()
