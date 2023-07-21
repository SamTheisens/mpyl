"""Health check command"""

import click
from rich.console import Console

from . import create_console_logger
from .commands.health.checks import perform_health_checks


@click.command("health")
@click.option(
    "--ci",
    is_flag=True,
    default=False,
    help="Run health checks relevant only for CI builds.",
)
def health(ci):
    """Health check"""
    console: Console = create_console_logger(local=False, verbose=False)
    perform_health_checks(console, ci)
