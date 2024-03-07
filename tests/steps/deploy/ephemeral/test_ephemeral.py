from pathlib import Path

from mpyl.project_execution import ProjectExecution
from src.mpyl.project import load_project, get_env_variables
from src.mpyl.steps.models import Input
from tests import root_test_path
from tests.test_resources import test_data


class TestEphemeral:
    resource_path = root_test_path / "projects" / "ephemeral" / "deployment"

    def test_get_env_variables_for_target(self):
        step_input = Input(
            ProjectExecution(
                load_project(self.resource_path, Path("project.yml"), True), frozenset()
            ),
            test_data.RUN_PROPERTIES,
            None,
        )
        assert step_input.project_execution.project.deployment is not None
        assert len(step_input.project_execution.project.deployment.properties.env) == 4

        env_variables = get_env_variables(
            step_input.project_execution.project, test_data.RUN_PROPERTIES.target
        )
        assert len(env_variables) == 4
