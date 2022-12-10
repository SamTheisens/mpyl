from logging import Logger

import yaml

from src.pympl.project import load_project
from src.pympl.repo import Repository, RepoConfig, History
from src.pympl.stage import Stage
from src.pympl.stages.discovery import find_invalidated_projects_for_stage
from src.pympl.steps.models import BuildProperties, VersioningProperties
from src.pympl.steps.steps import Steps

import logging
from rich.logging import RichHandler
from rich.console import Console

from src.pympl.target import Target


def main(repo: Repository, log: Logger):
    changes_in_branch: list[History] = repo.changes_in_branch()
    project_paths = repo.find_projects()
    logging.info(f" Projects: {len(project_paths)}")

    log.info(f" Build stage: {len(find_invalidated_projects_for_stage(repo, Stage.BUILD, changes_in_branch))}")
    log.info(f" Test stage: {len(find_invalidated_projects_for_stage(repo, Stage.TEST, changes_in_branch))}")
    log.info(f" Deploy stage: {len(find_invalidated_projects_for_stage(repo, Stage.DEPLOY, changes_in_branch))}")
    log.info(
        f" Post deploy stage: {len(find_invalidated_projects_for_stage(repo, Stage.POST_DEPLOY, changes_in_branch))}")
    all_projects = list(map(lambda p: load_project(".", p, False), project_paths))
    executor = Steps(logger=log)
    log.info(" Building projects")
    build_props = BuildProperties("1", Target.PULL_REQUEST, VersioningProperties(repo.get_sha, "1234", None))
    for proj in find_invalidated_projects_for_stage(repo, Stage.BUILD, changes_in_branch):
        executor.execute(Stage.BUILD, proj, build_props)
    for proj in find_invalidated_projects_for_stage(repo, Stage.DEPLOY, changes_in_branch):
        executor.execute(Stage.DEPLOY, proj, build_props)


if __name__ == "__main__":
    FORMAT = "%(name)s  %(message)s"
    logging.basicConfig(
        level="INFO", format=FORMAT, datefmt="[%X]",
        handlers=[RichHandler(markup=True, console=Console(width=255), show_path=True)]
    )

    with open("config.yml") as f:
        yaml_values = yaml.load(f, Loader=yaml.FullLoader)
        main(Repository(RepoConfig(yaml_values)), logging.getLogger("mpl"))
