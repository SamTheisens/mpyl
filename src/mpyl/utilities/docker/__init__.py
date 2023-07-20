"""Docker related utility methods"""
import logging
import shlex

from dataclasses import dataclass
from logging import Logger
from traceback import print_exc
from typing import Dict, Optional, Iterator, cast, Union
import shutil
from pathlib import Path
from python_on_whales import docker, Image, Container, DockerException
from python_on_whales.exceptions import NoSuchContainer
from rich.logging import RichHandler

from ..logging import try_parse_ansi
from ...project import Project
from ...steps.models import Input


@dataclass(frozen=True)
class DockerComposeConfig:
    period_seconds: int
    failure_threshold: int

    @property
    def total_duration(self):
        return self.period_seconds * self.failure_threshold

    @staticmethod
    def from_yaml(config: dict):
        compose_config = config.get("docker", {}).get("compose")
        if not compose_config:
            raise KeyError("docker.compose needs to be defined")
        return DockerComposeConfig(
            period_seconds=int(compose_config["periodSeconds"]),
            failure_threshold=int(compose_config["failureThreshold"]),
        )


@dataclass(frozen=True)
class DockerCacheConfig:
    cache_to: str
    cache_from: str

    @staticmethod
    def from_dict(config: Dict):
        return DockerCacheConfig(config["to"], config["from"])


@dataclass(frozen=True)
class DockerConfig:
    host_name: str
    organization: Optional[str]
    user_name: str
    password: str
    cache: Optional[DockerCacheConfig]
    root_folder: str
    build_target: Optional[str]
    test_target: Optional[str]
    docker_file_name: str

    @staticmethod
    def from_dict(config: Dict):
        try:
            registry: Dict = config["docker"]["registry"]
            build_config: Dict = config["docker"]["build"]
            return DockerConfig(
                host_name=registry["hostName"],
                user_name=registry["userName"],
                organization=registry.get("organization", None),
                cache=DockerCacheConfig.from_dict(registry["cache"])
                if "cache" in registry
                else None,
                password=registry["password"],
                root_folder=build_config["rootFolder"],
                build_target=build_config.get("buildTarget", None),
                test_target=build_config.get("testTarget", None),
                docker_file_name=build_config["dockerFileName"],
            )
        except KeyError as exc:
            raise KeyError(f"Docker config could not be loaded from {config}") from exc


def execute_with_stream(
    logger: Logger,
    container: Container,
    command: str,
    task_name: str,
    multiprocess: bool = False,
):
    if multiprocess:  # Logger settings need to be re-applied in each process
        logger.setLevel(logging.INFO)
        logger.addHandler(RichHandler())

    result = cast(
        Iterator[tuple[str, bytes]],
        container.execute(command=shlex.split(command), stream=True),
    )
    result_list = stream_docker_logging(logger, result, task_name)

    logger.handlers.clear()

    return result_list


def stream_docker_logging(
    logger: Logger,
    generator: Union[Iterator[str], Iterator[tuple[str, bytes]]],
    task_name: str,
    level=logging.INFO,
) -> list[str]:
    copied_logs = []

    while True:
        try:
            next_item = next(generator)
            log_line = (
                next_item[1].decode(errors="replace")
                if isinstance(next_item, tuple)
                else next_item
            )
            copied_logs.append(log_line)
            logger.log(level, try_parse_ansi(log_line))
        except StopIteration:
            logger.info(f"{task_name} complete.")
            return copied_logs


def docker_image_tag(step_input: Input):
    git = step_input.run_properties.versioning
    tag = git.tag if git.tag else f"pr-{git.pr_number}"
    return f"{step_input.project.name.lower()}:{tag}".replace("/", "_")


def docker_registry_path(docker_config: DockerConfig, image_name: str) -> str:
    path_components = [
        docker_config.host_name,
        docker_config.organization,
        image_name,
    ]
    return "/".join([c for c in path_components if c]).lower()


def docker_file_path(project: Project, docker_config: DockerConfig):
    return f"{project.deployment_path}/{docker_config.docker_file_name}"


def docker_copy(
    logger: Logger, container_path: str, dst_path: str, container: Container
):
    """
    Copies the contents of the specified path within the container to a locally created destination

    :param logger: the logger
    :param container_path: the path of the directory in the container to copy
    :param dst_path: the path to copy the container content to
    :param container: the container to copy from
    """
    shutil.rmtree(dst_path, ignore_errors=True)
    Path(dst_path).mkdir(parents=True, exist_ok=True)

    if not docker.container.exists(container.id):
        raise ValueError(f"Container {container.id} does not exist")

    logger.info(
        f"Copying contents from container {container.id} at "
        f"path {container_path} to host at {dst_path}"
    )
    try:
        docker.copy(f"{container.id}:{container_path}", dst_path)
    except NoSuchContainer as exc:
        logger.warning(
            f"Could not find data in container {container.name} at expected location {container_path}"
        )
        raise exc


def build(
    logger: Logger,
    root_path: str,
    file_path: str,
    image_tag: str,
    target: str,
    cache: Optional[DockerCacheConfig] = None,
) -> bool:
    """
    :param cache: optionally specify cache configuration
    :param logger: the logger
    :param root_path: the root path to which `docker_file_path` is relative
    :param file_path: path to the docker file to be built
    :param image_tag: the tag of the image
    :param target: the 'target' within the multi-stage docker image
    :return: True if success, False if failure
    """
    logger.info(f"Building docker image with {file_path} and target {target}")

    try:
        logs = docker.buildx.build(
            context_path=root_path,
            file=file_path,
            tags=[image_tag],
            target=target,
            stream_logs=False,
            cache_from=cache.cache_from if cache else None,
            cache_to=cache.cache_to if cache else None,
        )
        if logs is not None and not isinstance(logs, Image):
            stream_docker_logging(
                logger=logger, generator=logs, task_name=f"Build {file_path}:{target}"
            )
        logger.debug(logs)
        return True

    except DockerException as exc:
        command = " ".join(exc.docker_command)
        logger.warning(
            f"Docker build failed with command {command} and exit code {exc.return_code}"
        )
        return False
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"Docker build failed with {exc.__class__.__name__}")
        print_exc()
        return False


def login(logger: Logger, docker_config: DockerConfig) -> None:
    logger.info(f"Logging in with user '{docker_config.user_name}'")
    docker.login(
        server=f"https://{docker_config.host_name}",
        username=docker_config.user_name,
        password=docker_config.password,
    )
    logger.debug(f"Logged in as '{docker_config.user_name}'")


def create_container(logger: Logger, image_name: str) -> Container:
    logger.info(f"Creating container from image {image_name}")
    container = docker.create(image_name)
    logger.info(f"Created container {container.id}")

    return container


def remove_container(logger: Logger, container: Container) -> None:
    logger.info(f"Removing container {container.id}")
    docker.remove(container.id)
    logger.info(f"Removed container {container.id}")
