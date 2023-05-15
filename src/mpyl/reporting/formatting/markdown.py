"""
Markdown run result formatters
"""
import operator

from junitparser import TestSuite

from ...project import Stage, Project
from ...steps import Output, ArtifactType
from ...steps.deploy.kubernetes import DEPLOYED_SERVICE_KEY
from ...steps.run import RunResult
from ...steps.steps import StepResult, collect_test_results
from ...utilities.junit import TestRunSummary, sum_suites


def summary_to_markdown(summary: TestRunSummary):
    return f"🧪 {summary.tests} ❌ {summary.failures} " \
           f"💔 {summary.errors} 🙈 {summary.skipped}"


def __add_link(name: str, output: Output) -> str:
    if output.produced_artifact and output.produced_artifact.artifact_type == ArtifactType.DEPLOYED_HELM_APP:
        url = output.produced_artifact.spec.get(DEPLOYED_SERVICE_KEY)
        if url:
            return f'[{name}]({url}/swagger/index.html)'

    return name


def __to_oneliner(result: list[StepResult], plan: set[Project]) -> str:
    project_names: list[str] = []
    if plan:
        sorted_plan = sorted(plan, key=operator.attrgetter('name'))
        for proj in sorted_plan:
            found_result = next((r for r in result if r.project.name == proj.name), None)
            if found_result:
                project_names.append(f'*{__add_link(proj.name, found_result.output)}*' if found_result.output.success
                                     else f'~~{proj.name}~~')
            else:
                project_names.append(f'_{proj.name}_')
    else:
        project_names = list(map(lambda r: f'_{r.project.name}_', result))

    return f'{", ".join(project_names)}'


def stage_to_icon(stage: Stage):
    if stage == Stage.BUILD:
        return '🏗️ '
    if stage == Stage.TEST:
        return '🧪'
    if stage == Stage.DEPLOY:
        return '🚀'
    return '➡️'


def markdown_for_stage(run_result: RunResult, stage: Stage):
    step_results: list[StepResult] = run_result.results_for_stage(stage)
    plan: set[Project] = run_result.plan_for_stage(stage)
    result = ""
    if step_results or plan:
        result += f"{stage_to_icon(stage)}  {__to_oneliner(step_results, plan)}  \n"
        test_results = collect_test_results(step_results)
        if test_results:
            result += to_markdown_test_report(
                test_results) + f' [link]({run_result.run_properties.details.tests_url}) \n'

    return result


def run_result_to_markdown(run_result: RunResult) -> str:
    result: str = f'{run_result.status_line}  \n'
    exception = run_result.exception
    if exception:
        result += f"For _{exception.executor}_ on _{exception.project_name}_ at _{exception.stage}_ \n"
        result += f"\n```\n{exception}\n```\n"

    for stage in Stage:
        result += markdown_for_stage(run_result, stage)

    return result


def to_markdown_test_report(suites: list[TestSuite]):
    total_tests = sum_suites(suites)
    return f"{summary_to_markdown(total_tests)}"
