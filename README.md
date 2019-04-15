# `decisionlib`

Taskcluster utility library for building reusable tasks.

:rotating_light: Note: this is experimental, and we might not use this within releng :rotating_light:

### Example

```python
from decisionlib.decision import *

def main():
    scheduler = Scheduler()
    assemble_task_id = shell_task('assemble', 'mozillamobile/fenix:1.0', './gradlew assembleRelease') \
        .append_artifact(AndroidArtifact('public/target.apk', 'release/app-release.apk')) \
        .with_treeherder('build', 'android-all', 1, 'B') \
        .with_notify_owner() \
        .schedule(scheduler)
    
    sign_task('sign', 'autograph_apk', SigningType.DEP, [(assemble_task_id, ['public/target.apk'])]) \
        .with_treeherder('other', 'android-all', 1, 'S') \
        .with_notify_owner() \
        .append_route('index.project.mobile.fenix.release.latest') \
        .schedule(scheduler)
        
    queue = taskcluster.Queue() # Fill in real queue parameters
    trigger = Trigger.from_environment()
    checkout = Checkout.from_cwd()
    scheduler.schedule_tasks(queue, trigger, checkout)
```

### Usage:

1. `pip install decisionlib-mhentges`
2. Write your python to schedule tasks, such as shown in the example above
3. Run your python script on Taskcluster, such as with a [hook](https://taskcluster-web.netlify.com/hooks)
