"""Camunda cluster related docker commands to deploy diagrams"""

import os
from logging import Logger
from ....utilities.bpm import CamundaConfig
from ....utilities.subprocess import custom_check_output


def deploy_diagram_to_cluster(logger: Logger, config: CamundaConfig):
    bpm_file_path = config.deployment_path.bpm_diagram_folder_path

    for file_name in (
        [fn for fn in os.listdir(bpm_file_path) if fn.endswith(".bpmn")]
        if os.path.isdir(bpm_file_path)
        else []
    ):
        relative_file_path = os.path.join(bpm_file_path, file_name)

        logger.info(f"Deploying {relative_file_path}")

        command = (
            f"zbctl deploy {relative_file_path} "
            f"--address {config.zeebe_credentials.cluster_id} "
            f"--clientId {config.zeebe_credentials.client_id} "
            f"--clientSecret {config.zeebe_credentials.client_secret}"
        )

        custom_check_output(logger, command)
