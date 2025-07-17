# Copyright 2025 Camptocamp
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)

import click
from ..app import App


@click.group()
def cli():
    pass


@cli.command()
@click.argument("source", required=True)
@click.argument("target", required=True)
@click.argument("addon_path", required=True)
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
    addon_path: str,
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

        $ oca-port-analyze origin/18.0 origin/17.0 ./addons/delivery
    """
    try:
        app = App(
            source=source,
            target=target,
            addon_path=addon_path,
            upstream_org="odoo",
            output=output,
            cli=True,
            skip_commit=False,
            min_lines=min_lines,
            fetch=True,
        )
        app.run_analyze()
    except ValueError as exc:
        raise click.ClickException(exc) from exc


if __name__ == "__main__":
    cli()
