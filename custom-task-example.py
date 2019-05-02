from decisionlib.decisionlib import ShellTask, Artifact, ArtifactType


class MavenShellTask(ShellTask):
    def __init__(self, task_name: str, provisioner_id: str, worker_type: str, mvn_goal: str):
        super().__init__(task_name, provisioner_id, worker_type, 'mozillamobile/maven:15.0',
                         'mvn {}'.format(mvn_goal))

    def with_surefire_artifacts(self):
        self.with_artifact(Artifact('public/tests', 'target/surefire-reports',
                                    ArtifactType.DIRECTORY))
        return self
