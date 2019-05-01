# `decisionlib`

Taskcluster utility library for building reusable tasks.

:rotating_light: Note: this is experimental, and we might not use this within releng :rotating_light:

## Within decision task

### Example

```python
from decisionlib.decisionlib import Scheduler, mobile_shell_task, AndroidArtifact, sign_task, \
    SigningType, Trigger, Checkout, TaskclusterQueue


def main():
    scheduler = Scheduler()
    assemble_task_id = mobile_shell_task('assemble', 'mozillamobile/fenix:1.0',
                                         './gradlew assembleRelease', 'ref-browser') \
        .with_artifact(AndroidArtifact('public/target.apk', 'release/app-release.apk')) \
        .with_treeherder('build', 'android-all', 1, 'B') \
        .with_notify_owner() \
        .schedule(scheduler)

    sign_task('sign', 'autograph_apk', SigningType.DEP,
              [(assemble_task_id, ['public/target.apk'])]) \
        .with_treeherder('S', 'other', 'android-all', 1) \
        .with_notify_owner() \
        .with_route('index.project.mobile.fenix.release.latest') \
        .schedule(scheduler)

    queue = TaskclusterQueue.from_environment()
    trigger = Trigger.from_environment()
    checkout = Checkout.from_environment()
    scheduler.schedule_tasks(queue, checkout, trigger)
```

## Within hook

Update `payload.command`  of your hook to run `pip install decisionlib && decisionlib schedule-hook`

## Within shell task

`decisionlib` has the ability to fetch secrets from taskcluster from either the command line or via python import.

`pip install decisionlib && decisionlib get-secret /project/mobile/fenix/sentry api_key`

### Usage:

1. `pip install decisionlib-mhentges`
2. Write your python decision task to schedule tasks
3. Run your python script on Taskcluster, such as with a [hook](https://taskcluster-web.netlify.com/hooks)
