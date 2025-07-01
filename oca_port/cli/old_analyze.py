# Copyright 2023 Camptocamp SA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)

import os
import re
import click
import git
import json
from ..app import App


def parse_comma_separated(ctx, param, value):
    if value:
        return [x.strip() for x in value.split(",")]
    return []


# TODO: option to filter category output, use regex?
@click.command()
@click.argument("source", required=True)
@click.argument("target", required=True)
@click.argument("repo_path", required=True)
@click.argument("addons", callback=parse_comma_separated, required=True)
@click.option(
    "--output",
    help=(
        "Returns the result in a given format. "
        "This implies the `--non-interactive` option automatically. "
        "Possibles values are: 'json'."
    ),
)
@click.option(
    "--min_lines",
    default=0,
    help="Enable to only take into account commits with a diff >= min-lines",
)
def analyze(
    source: str,
    target: str,
    repo_path: str,
    addons: str,
    output,
    min_lines,
):
    """
    source:
        string representation of the source branch, e.g. 'origin/18.0'
    target:
        string representation of the target branch, e.g. 'origin/16.0'
    addon_path:
        the path of the addon to process

    E.g.: to see what's new in 18.0 when you are using 17.0

        $ oca-port-analyze origin/18.0 origin/17.0 addons/delivery
    """
    # generate a heatmap of odoo native changes
    for addon in addons:
        try:
            # TODO: anyway to remove addons?
            addon_path = f"{repo_path}/addons/{addon}"
            app = App(
                addon_path=addon_path,
                source=source,
                target=target,
                repo_path=repo_path,
                upstream_org="Odoo",
                non_interactive=True,
                output=output,
                cli=True,
                min_lines=min_lines,
            )
            app.run_analyze()
        except ValueError as exc:
            raise click.ClickException(exc) from exc


if __name__ == "__main__":
    analyze()
