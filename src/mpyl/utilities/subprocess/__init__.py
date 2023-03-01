"""Utilities related to launching a subprocess"""

import subprocess
from logging import Logger

from ...steps.models import Output


def custom_check_output(logger: Logger, command: list[str]) -> Output:
    command_argument = ' '.join(command)
    logger.info(f"Executing: '{command_argument}'")
    try:
        with subprocess.Popen(command, stdout=subprocess.PIPE, text=True) as process:
            if not process.stdout:
                raise RuntimeError(f'Process {command_argument} does not have an stdout')

            for line in iter(process.stdout.readline, ""):
                if line:
                    print(line.strip())
                if process.poll() is not None:
                    break
            exit_code = process.wait()

            return Output(success=exit_code == 0, message='Subprocess executed successfully')

    except subprocess.CalledProcessError as exc:
        message = f"'{command_argument}': failed with return code: {exc.returncode} err: {exc.stderr.decode()}"
        logger.warning(message, exc_info=True)

    return Output(success=False, message='Subprocess failed')
