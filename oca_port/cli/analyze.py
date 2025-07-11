# Copyright 2025 Camptocamp
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)

import click
from ..app import App
from ..utils.misc import list_versions_between, find_module_path
from collections import defaultdict
import pandas as pd
import plotly.express as px
from dash import Dash, html, dcc

CELL_HEIGHT = 45
CELL_WIDTH = 110
HEIGHT_PADDING = 100
WIDTH_PADDING = 200


@click.group()
def cli():
    pass


def list_odoo_addons(ctx, param, value):
    if value:
        return [x.strip() for x in value.split(",")]
    return []


def show_heatmap(data):
    click.echo("Starting Dash application....")
    df = pd.DataFrame(data)
    df = df.sort_values(by=["Version", "Addon"])

    num_addons = len(df["Addon"].unique())
    num_versions = len(df["Version"].unique())

    fig_height = (num_addons * CELL_HEIGHT) + HEIGHT_PADDING
    fig_width = (num_versions * CELL_WIDTH) + WIDTH_PADDING

    # plotly config
    fig = px.imshow(
        df.pivot(index="Addon", columns="Version", values="Total Commits"),
        labels=dict(
            x="Version",
            y="Addon",
            color="Total Commits",
        ),
        x=df["Version"].unique(),
        y=df["Addon"].unique(),
        color_continuous_scale="Viridis",
        text_auto=True,
        aspect="auto",
    )
    fig.update_xaxes(side="top")
    fig.update_coloraxes(colorbar_tickformat=".0f")
    fig.update_layout(
        width=fig_width,
        height=fig_height,
        font=dict(size=14),
    )

    # dash config
    app = Dash(__name__)
    app.layout = html.Div(
        style={
            "fontFamily": "Inter, sans-serif",
            "padding": "20px",
            "margin": "auto",
            "backgroundColor": "#f9f9f9",
            "borderRadius": "8px",
            "boxShadow": "0 4px 8px rgba(0,0,0,0.1)",
        },
        children=[
            html.H1(
                "Odoo Addon Commits Heatmap",
                style={"textAlign": "center", "color": "#333", "marginBottom": "10px"},
            ),
            html.Div(
                style={"display": "flex", "justifyContent": "center"},
                children=[
                    dcc.Graph(
                        figure=fig,
                    ),
                ],
            ),
        ],
    )
    app.run(debug=True, port=8050)


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


@cli.command()
@click.argument("source", required=True)
@click.argument("target", required=True)
@click.argument("repo_path", required=True)
@click.argument("addons", callback=list_odoo_addons, required=True)
@click.option(
    "--min_lines",
    default=0,
    help="Enable to only take into account commits with a diff >= min-lines",
)
def generate_heatmap(source, target, repo_path, addons, min_lines):
    """
    source:
        string representation of the source branch, e.g. 'origin/18.0'
    target:
        string representation of the target branch, e.g. 'origin/16.0'
    repo_path:
        local path to the Git repository
    addons:
        list of addons name separated by comma, e.g: account,delivery

    E.g.: to generate a heatmap of total commits from 15.0 to 18.0

        $ oca-port-analyze generate-heatmap origin/18.0 origin/15.0 ./ account,delivery
    """
    all_versions = list_versions_between(source, target)
    heatmap_data = defaultdict(dict)
    for addon in addons:
        addon_path = find_module_path(repo_path, addon)
        for i in range(len(all_versions) - 1):
            current_source_version = all_versions[i]
            current_target_version = all_versions[i + 1]
            try:
                app = App(
                    source=current_source_version,
                    target=current_target_version,
                    addon_path=addon_path,
                    upstream_org="odoo",
                    output="json",
                    cli=True,
                    skip_commit=False,
                    min_lines=min_lines,
                    fetch=True,
                )
                result = app.run_heatmap()
                heatmap_data[addon][current_source_version] = result.get(
                    current_source_version
                )
                heatmap_data[addon][current_target_version] = result.get(
                    current_target_version
                )
            except ValueError as exc:
                raise click.ClickException(exc) from exc

    rows = []
    for addon_name, versions in heatmap_data.items():
        for version, count in versions.items():
            rows.append(
                {
                    "Addon": addon_name,
                    "Version": version,
                    "Total Commits": count,
                }
            )
    show_heatmap(data=rows)


if __name__ == "__main__":
    cli()
