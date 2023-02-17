from dataclasses import dataclass

from dagster import job, op, DynamicOut, DynamicOutput, get_dagster_logger, Output, Failure
from pyaml_env import parse_config

from src.mpyl.project import load_project, Project, Stage
from src.mpyl.steps.models import Output as MplOutput
from src.mpyl.repo import Repository, RepoConfig
from src.mpyl.reporting.simple import to_string
from src.mpyl.reporting.targets.github import GithubReport
from src.mpyl.steps.models import RunProperties
from src.mpyl.steps.run import RunResult
from src.mpyl.steps.steps import Steps, StepResult


@dataclass
class StepParam:
    stage: Stage
    project: Project


def execute_step(proj: Project, stage: Stage) -> StepResult:
    config = parse_config("config.yml")
    properties = parse_config("run_properties.yml")
    run_properties = RunProperties.from_configuration(run_properties=properties, config=config)
    dagster_logger = get_dagster_logger()
    executor = Steps(dagster_logger, run_properties)
    step_result = executor.execute(stage, proj)
    if not step_result.output.success:
        raise Failure(description=step_result.output.message)
    return step_result


@op
def build_project(project: Project) -> Output:
    return Output(execute_step(project, Stage.BUILD))


@op
def test_project(project: Project) -> Output:
    return Output(execute_step(project, Stage.TEST))


@op
def deploy_project(project: Project) -> Output:
    return Output(execute_step(project, Stage.DEPLOY))


@op
def deploy_projects(projects: list[Project], outputs: list[StepResult]) -> Output[list[StepResult]]:
    res = []
    for proj in projects:
        res.append(execute_step(proj, Stage.DEPLOY))
    return Output(res)


@op
def report_results(build_results: list[StepResult], deploy_results: list[StepResult]) -> bool:
    config = parse_config("config.yml")

    properties = RunProperties.from_configuration(parse_config("run_properties.yml"), config)

    run_result = RunResult(properties)
    run_result.extend(build_results)
    run_result.extend(deploy_results)

    logger = get_dagster_logger()
    logger.info(to_string(run_result))

    report = GithubReport(config)
    report.send_report(run_result)
    return True


@op(out=DynamicOut())
def find_projects() -> list[DynamicOutput[Project]]:
    yaml_values = parse_config("config.yml")
    repo = Repository(RepoConfig(yaml_values))
    project_paths = repo.find_projects()
    projects = map(lambda p: load_project(".", p), project_paths)
    return list(map(lambda project: DynamicOutput(project, mapping_key=project.name), projects))


@job
def run_build():
    projects = find_projects()
    build_results = projects.map(build_project)
    deploy_results = deploy_projects(
        projects=projects.collect(),
        outputs=build_results.collect()
    )
    report_results(build_results=build_results.collect(), deploy_results=deploy_results)


if __name__ == "__main__":

    result = run_build.execute_in_process()
    print(f"Result: {result.success}")
