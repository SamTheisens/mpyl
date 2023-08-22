""" This module is called on to create a helm chart for your project and install it during the `mpyl.steps.deploy`
step.
"""

import shutil
from logging import Logger
from pathlib import Path

import yaml

from .resources import to_yaml, CustomResourceDefinition
from ...models import RunProperties, Output
from ....cli import get_version
from ....utilities.subprocess import custom_check_output


def to_chart_metadata(chart_name: str, run_properties: RunProperties):
    mpyl_version = get_version()
    return f"""apiVersion: v3
name: {chart_name}
description: |
    A helm chart rendered by an MPyL k8s deploy step. 
    The version of this chart is the version of the MPyL release used to create this chart
type: application
version: {mpyl_version}
appVersion: "{run_properties.versioning.identifier}"
"""

GENERATED_WARNING = """# This file was generated by MPyL. DO NOT EDIT DIRECTLY."""

def add_repo(logger: Logger, repo_name: str, repo_url: str):
    cmd_add = f"helm repo add {repo_name} {repo_url}"
    return custom_check_output(logger, cmd_add)


def update_repo(logger: Logger):
    return custom_check_output(logger, "helm repo update")


def write_chart(
    chart: dict[str, CustomResourceDefinition],
    chart_path: Path,
    chart_metadata: str,
    values: dict[str, str],
) -> None:
    shutil.rmtree(chart_path, ignore_errors=True)
    template_path = chart_path / Path("templates")
    template_path.mkdir(parents=True, exist_ok=True)

    with open(chart_path / Path("Chart.yaml"), mode="w+", encoding="utf-8") as file:
        file.write(chart_metadata)
    with open(chart_path / Path("values.yaml"), mode="w+", encoding="utf-8") as file:
        if values == {}:
            file.write(
                "# This file is intentionally left empty. All values in /templates have been pre-interpolated"
            )
        else:
            file.write(yaml.dump(values))

    my_dictionary: dict[str, str] = dict(
        map(lambda item: (item[0], to_yaml(item[1])), chart.items())
    )

    for name, template_content in my_dictionary.items():
        with open(template_path / name, mode="w+", encoding="utf-8") as file:
            file.write(f"{GENERATED_WARNING}\n{template_content}")


def __remove_existing_chart(
    logger: Logger, chart_name: str, name_space: str, kube_context: str
) -> Output:
    found_chart = custom_check_output(
        logger, f"helm list -f ^{chart_name}$ -n {name_space}", capture_stdout=True
    )
    if chart_name in found_chart.message:
        cmd = (
            f"helm uninstall {chart_name} -n {name_space} --kube-context {kube_context}"
        )
        return custom_check_output(Logger("helm"), cmd)
    return Output(
        success=True, message=f"No existing chart {chart_name} found to delete"
    )


def __execute_install_cmd(
    logger: Logger,
    step_input: Input,
    chart_name: str,
    name_space: str,
    kube_context: str,
    delete_existing: bool = False,
    additional_args: str = "",
) -> Output:
    if delete_existing:
        removed = __remove_existing_chart(logger, chart_name, name_space, kube_context)
        if not removed.success:
            return removed

    cmd = f"helm upgrade -i {chart_name} -n {name_space} --kube-context {kube_context} {additional_args}"
    if step_input.dry_run:
        cmd = (
            f"helm upgrade -i {chart_name} -n namespace --kube-context {kube_context} {additional_args} "
            f"--debug --dry-run"
        )
    return custom_check_output(logger, cmd)


def install_with_values_yaml(
    logger: Logger,
    step_input: Input,
    values: dict,
    release_name: str,
    chart_name: str,
    namespace: str,
    kube_context: str,
) -> Output:
    values_path = Path(step_input.project.target_path)
    logger.info(f"Writing Helm values to {values_path}")

    write_chart({}, values_path, "", values)

    values_path_arg = f'-f {values_path / Path("values.yaml")} {chart_name}'
    if step_input.dry_run:
        values_path_arg += " --debug --dry-run"
    return __execute_install_cmd(
        logger,
        step_input,
        release_name,
        namespace,
        kube_context,
        False,
        additional_args=values_path_arg,
    )


def write_helm_chart(
    logger: Logger,
    chart: dict[str, CustomResourceDefinition],
    target_path: Path,
    run_properties: RunProperties,
    chart_name: str,
) -> Path:
    chart_path = Path(target_path) / "chart"
    logger.info(f"Writing HELM chart to {chart_path}")
    write_chart(chart, chart_path, to_chart_metadata(chart_name, run_properties))
    return chart_path


def template(logger: Logger, chart_path: Path, name_space: str) -> Output:
    cmd = f"helm template -n {name_space} {chart_path}"
    output = custom_check_output(logger, cmd, capture_stdout=True)
    template_file = chart_path / "template.yml"
    template_file.write_text(f"{GENERATED_WARNING}\n{output.message}")
    return Output(success=True, message=f"Chart templated to {template_file}")


def install(
    logger: Logger,
    chart_path: Path,
    dry_run: bool,
    release_name: str,
    name_space: str,
    kube_context: str,
    delete_existing: bool = False,
) -> Output:
    if delete_existing:
        removed = __remove_existing_chart(
            logger, release_name, name_space, kube_context
        )
        if not removed.success:
            return removed

    additional_args = str(chart_path)
    if dry_run:
        additional_args += " --debug --dry-run"
    return __execute_install_cmd(
        logger,
        step_input,
        release_name,
        name_space,
        kube_context,
        delete_existing,
        additional_args=additional_args,
    )
