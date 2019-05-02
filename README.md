from decisionlib.decisionlib import ShellTaskfrom decisionlib.decisionlib import ShellTask# `decisionlib`

Taskcluster utility library for building reusable tasks.

:rotating_light: Note: this is experimental, and we might not use this within releng :rotating_light:

## Within decision task

### Example

```python
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
```

## Within hook

Update `payload.command`  of your hook to run `pip install decisionlib && decisionlib schedule-hook`

## Within shell task

`decisionlib` has the ability to fetch secrets from taskcluster from either the command line or via python import.

`pip install decisionlib && decisionlib get-secret /project/mobile/fenix/sentry api_key`

### Usage:

1. `pip install decisionlib-mhentges`
2. Write your python decision task to schedule tasks
3. Run your python script on Taskcluster, such as with a hook ([such as this `reference-browser` staging hook](https://tools.taskcluster.net/hooks/project-mobile/reference-browser-nightly-staging))

### Creating your own task types

If your task type always runs as a script within a Docker image, you should extend `ShellTask` (example below).
Otherwise, if your task type revolves around a particular worker type with a payload (e.g.: for `mobile-pushapk` tasks),
you probably want to extend the base `Task`.

```python
from typing import Optional

from decisionlib.decisionlib import ShellTask, Artifact, ArtifactType, SlugId, Trigger, Checkout


class MavenShellTask(ShellTask):
    _mvn_goal: str
    _parallel: bool
    _parallel_thread_count: Optional[int]

    def __init__(self, task_name: str, provisioner_id: str, worker_type: str, mvn_goal: str):
        super().__init__(task_name, provisioner_id, worker_type, 'mozillamobile/maven:15.0')
        self._mvn_goal = mvn_goal
        self._parallel = False

    def with_surefire_artifacts(self):
        self.with_artifact(Artifact('public/tests', 'target/surefire-reports',
                                    ArtifactType.DIRECTORY))
        return self

    def with_parallel(self, thread_count: int):
        # Maybe not the best example, because you'd probably want maintainers to just
        # write the full "mvn" command itself, rather than having a function for each
        # option. However, this illustrates how render(...) would be overridden, and
        # that's the main point of this exercise, so :)
        self._parallel = True
        self._parallel_thread_count = thread_count
        return self

    def render(
            self,
            task_id: SlugId,
            trigger: Trigger,
            checkout: Checkout,
    ):
        self.with_script('mvn {} {}'.format(
            '-T {}'.format(self._parallel_thread_count) if self._parallel else '',
            self._mvn_goal
        ))
        return super().render(task_id, trigger, checkout)
        
        
def main():
    scheduler = ...
    MavenShellTask('test', 'provisioner', 'worker', 'test') \
        .with_surefire_artifacts() \
        .with_parallel(4) \
        .schedule(scheduler)
    ...
```
