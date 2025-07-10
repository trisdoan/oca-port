# Copyright 2023 Camptocamp SA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)

import os
import re
import click
import git
import json
from ..app import App
from collections import defaultdict
import tempfile
import subprocess
from ..utils.misc import Output, bcolors as bc, extract_ref_info


def parse_comma_separated(ctx, param, value):
    if value:
        return [x.strip() for x in value.split(",")]
    return []


def _get_odoo_versions_between(source_version_str, target_version_str):
    """
    Parses Odoo version strings (e.g., '15.0') and returns a list of versions
    between them, inclusive.
    """

    def parse_version(version_str):
        major, minor = map(int, version_str.split("."))
        return major * 10 + minor  # Convert 15.0 to 150, 16.0 to 160

    def format_version(version_int):
        major = version_int // 10
        minor = version_int % 10
        return f"{major}.{minor}"

    source_int = parse_version(source_version_str)
    target_int = parse_version(target_version_str)
    if source_int > target_int:
        source_int, target_int = target_int, source_int

    versions = []
    for i in range(source_int, target_int + 1):
        major = i // 10
        minor = i % 10
        if minor == 0:
            versions.append(f"{major}.0")
    versions.reverse()
    return versions


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
@click.option(
    "--with-heatmap",
    is_flag=True,
    help="Generate a heatmap of line changes for a specific category across versions.",
)
@click.option(
    "--heatmap-category",
    default="local change",
    help="Specify the category of changes to visualize in the heatmap (default: 'local change').",
)
def analyze(
    source: str,
    target: str,
    repo_path: str,
    addons: str,
    output,
    min_lines,
    with_heatmap: bool,
    heatmap_category: str,
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
    if with_heatmap:

        repo = git.Repo(repo_path)
        ref_info = extract_ref_info(repo, "source", source)
        source_version = ref_info.get("branch")
        ref_info = extract_ref_info(repo, "target", target)
        target_version = ref_info.get("branch")

        all_versions = _get_odoo_versions_between(source_version, target_version)
        # Heatmap data structure: {addon: {version_transition: line_changes}}
        # e.g., {'delivery': {'15.0-16.0': 120, '16.0-17.0': 80}}
        heatmap_results = defaultdict(dict)

        for addon in addons:
            addon_path = f"{repo_path}/addons/{addon}"

            for i in range(len(all_versions) - 1):
                current_source_version = all_versions[i]
                current_target_version = all_versions[i + 1]
                print("current_source_version", current_source_version)
                print("current_target_version", current_target_version)

                try:
                    app = App(
                        addon_path=addon_path,
                        source=current_source_version,
                        target=current_target_version,
                        repo_path=repo_path,
                        upstream_org="Odoo",
                        non_interactive=True,
                        output="json",
                        cli=True,
                        min_lines=min_lines,
                    )
                    _, analysis_results = app.run_analyze()
                    print("analysis_results", analysis_results)
                    # analysis_results(
                    #     True,
                    #     '{"process": "analyze", "results": {"total_commits": 5, "total_line_changes": 20278, "categories": {"translations": {"commits": 5, "line_changes": 20278}}}}',
                    # )

                    # Extract line changes for the specified category
                    # Safely get nested dictionary values, defaulting to 0 if not found
                    # FIXME: implement category
                    category_data = analysis_results.get("results", {}).get(
                        "categories", {}
                    )
                    line_changes = category_data.get("translations")["line_changes"]

                    version_transition_key = (
                        f"{current_source_version}-{current_target_version}"
                    )
                    heatmap_results[addon][version_transition_key] = line_changes
                    print("heatmap_results", heatmap_results)

                except Exception as e:
                    click.echo(
                        f"smt wrong {e}",
                        err=True,
                    )

        # Save heatmap_results to a temporary JSON file
        # tempfile.NamedTemporaryFile creates a file that is automatically deleted
        # when it's closed (or the program exits), unless delete=False.
        # We set delete=False to ensure it persists for the subprocess.
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".json"
        ) as tmp_file:
            json.dump(heatmap_results, tmp_file)
            heatmap_data_path = tmp_file.name

        click.echo(f"Generated heatmap data saved to: {heatmap_data_path}")
        click.echo("Starting Dash heatmap application...")

        # Run the Dash app in a separate process
        # This assumes 'heatmap_generator.py' is in the same directory as 'analyze.py'
        # FIXME: it did not remove the tmp file
        try:
            # subprocess.run waits for the command to complete.
            # check=True raises CalledProcessError if the command returns a non-zero exit code.
            subprocess.run(
                [
                    "python",
                    os.path.join(os.path.dirname(__file__), "heatmap_generator.py"),
                    heatmap_data_path,
                    heatmap_category,
                ],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            click.ClickException(f"Failed to run heatmap generator: {e}")
        finally:
            # Clean up the temporary file after the Dash app finishes
            os.remove(heatmap_data_path)
            click.echo(f"Cleaned up temporary heatmap data file: {heatmap_data_path}")
    else:
        # Original behavior: analyze single source-target pair
        for addon in addons:
            try:
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
                # This will trigger the print_changes method within AnalyzeNativeChanges
                app.run_analyze()
            except ValueError as exc:
                raise click.ClickException(exc) from exc


if __name__ == "__main__":
    analyze()
