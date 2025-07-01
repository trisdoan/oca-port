import os
import re
import click
import git
import json
from oca_port.utils.misc import Output
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from ..app import App


def parse_comma_separated(ctx, param, value):
    if value:
        return [x.strip() for x in value.split(",")]
    return []


def analyze_single_module_version(source, target, repo_path, addon, min_lines=0):
    """Analyze a single module between two versions."""
    try:
        addon_path = f"{repo_path}/addons/{addon}"
        if not Path(addon_path).exists():
            return None

        app = App(
            addon_path=addon_path,
            source=source,
            target=target,
            repo_path=repo_path,
            upstream_org="Odoo",
            non_interactive=True,
            output="json",
            cli=True,
            min_lines=min_lines,
        )

        success, output = app.run_analyze()
        if success and output:
            result = json.loads(output) if isinstance(output, str) else output
            return {
                "addon": addon,
                "source": source,
                "target": target,
                "result": result,
            }
    except Exception as e:
        print(f"Error analyzing {addon} from {source} to {target}: {e}")
    return None


def generate_heatmap_data(results):
    """Convert analysis results to heatmap data."""
    heatmap_data = []

    for result in results:
        if not result:
            continue

        addon = result["addon"]
        source = result["source"]
        target = result["target"]
        analysis = result["result"]

        # Extract version from branch name (e.g., "origin/14.0" -> "14.0")
        version_match = re.search(r"(\d+\.\d+)", target)
        target_version = version_match.group(1) if version_match else target

        # Get local change commits count
        categories = analysis.get("results", {}).get("categories", {})
        local_changes = categories.get("local change", {}).get("commits", 0)
        total_commits = analysis.get("results", {}).get("total_commits", 0)
        total_lines = analysis.get("results", {}).get("total_line_changes", 0)

        heatmap_data.append(
            {
                "module": addon,
                "version": target_version,
                "local_changes": local_changes,
                "total_commits": total_commits,
                "total_lines": total_lines,
            }
        )

    return heatmap_data


def create_heatmap(data, output_path=None, title="Odoo Native Changes Heatmap"):
    """Create and save heatmap visualization."""
    if not data:
        print("No data available for heatmap generation")
        return

    # Create DataFrame
    df = pd.DataFrame(data)

    # Pivot table for heatmap
    pivot_table = df.pivot(index="module", columns="version", values="local_changes")
    pivot_table = pivot_table.fillna(0)

    # Sort versions properly (14.0, 15.0, 16.0, etc.)
    version_order = sorted(
        pivot_table.columns,
        key=lambda x: float(x) if x.replace(".", "").isdigit() else 0,
    )
    pivot_table = pivot_table[version_order]

    # Create heatmap
    plt.figure(figsize=(12, 8))
    sns.heatmap(
        pivot_table,
        annot=True,
        fmt="g",
        cmap="YlOrRd",
        cbar_kws={"label": "Number of Local Changes"},
        linewidths=0.5,
    )

    plt.title(title, fontsize=16, fontweight="bold")
    plt.xlabel("Odoo Version", fontsize=12)
    plt.ylabel("Module", fontsize=12)
    plt.xticks(rotation=45)
    plt.yticks(rotation=0)
    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        print(f"Heatmap saved to: {output_path}")
    else:
        plt.show()

    return pivot_table


def save_detailed_results(results, output_path):
    """Save detailed analysis results to JSON file."""
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Detailed results saved to: {output_path}")


# FIXME: re-design arg/option
@click.command()
@click.argument("repo_path", required=True)
@click.option(
    "--versions",
    default="14.0,15.0,16.0,17.0,18.0",
    help="Comma-separated list of Odoo versions to analyze",
    callback=parse_comma_separated,
)
@click.option(
    "--modules",
    default="account,delivery",
    help="Comma-separated list of modules to analyze",
    callback=parse_comma_separated,
)
@click.option(
    "--output-dir",
    default="./analysis_results",
    help="Directory to save output files",
)
@click.option(
    "--min-lines",
    default=0,
    help="Minimum lines changed to include a commit",
)
@click.option(
    "--max-workers",
    default=4,
    help="Maximum number of parallel workers",
)
@click.option(
    "--heatmap-only",
    is_flag=True,
    help="Only generate heatmap without detailed analysis",
)
@click.option(
    "--remote",
    default="origin",
    help="Git remote to use for branches",
)
def analyze(
    repo_path: str,
    versions: list,
    modules: list,
    output_dir: str,
    min_lines: int,
    max_workers: int,
    heatmap_only: bool,
    remote: str,
):
    """
    Generate a comprehensive heatmap of Odoo native changes across modules and versions.

    REPO_PATH: Path to the Odoo repository

    Examples:

    # Analyze all default modules and versions
    oca-port-analyze /path/to/odoo

    # Analyze specific modules and versions
    oca-port-analyze /path/to/odoo --modules account,sale --versions 16.0,17.0,18.0

    # Generate heatmap only (skip detailed analysis)
    oca-port-analyze /path/to/odoo --heatmap-only
    """

    # Validate repository
    try:
        repo = git.Repo(repo_path)
    except git.exc.InvalidGitRepositoryError:
        raise click.ClickException(f"Invalid Git repository: {repo_path}")

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Prepare version pairs for analysis
    version_pairs = []
    sorted_versions = sorted(versions, key=lambda x: float(x))

    for i in range(len(sorted_versions) - 1):
        source_version = sorted_versions[i + 1]  # Higher version (source)
        target_version = sorted_versions[i]  # Lower version (target)

        for module in modules:
            version_pairs.append(
                {
                    "source": f"{remote}/{source_version}",
                    "target": f"{remote}/{target_version}",
                    "module": module,
                }
            )

    print(
        f"Starting analysis of {len(modules)} modules across {len(sorted_versions)} versions"
    )
    print(f"Total analysis tasks: {len(version_pairs)}")
    print(f"Output directory: {output_path.absolute()}")

    results = []

    for pair in version_pairs:
        result = analyze_single_module_version(
            pair["source"], pair["target"], repo_path, pair["module"], min_lines
        )
        results.append(result)

    # Generate heatmap data
    heatmap_data = generate_heatmap_data(results)

    if not heatmap_only:
        detailed_output_path = output_path / "detailed_analysis.json"
        save_detailed_results(results, detailed_output_path)

        # Save heatmap data as CSV
        csv_output_path = output_path / "heatmap_data.csv"
        pd.DataFrame(heatmap_data).to_csv(csv_output_path, index=False)
        print(f"Heatmap data saved to: {csv_output_path}")

    # Generate and save heatmap
    heatmap_output_path = output_path / "odoo_changes_heatmap.png"
    pivot_table = create_heatmap(
        heatmap_data,
        heatmap_output_path,
        f"Odoo Native Changes - Local Changes per Module and Version",
    )

    # Generate additional heatmaps for total commits and lines
    if not heatmap_only:
        # Total commits heatmap
        commits_data = [
            {**item, "value": item["total_commits"]} for item in heatmap_data
        ]
        commits_df = pd.DataFrame(commits_data)
        commits_pivot = commits_df.pivot(
            index="module", columns="version", values="value"
        ).fillna(0)
        version_order = sorted(commits_pivot.columns, key=lambda x: float(x))
        commits_pivot = commits_pivot[version_order]

        plt.figure(figsize=(12, 8))
        sns.heatmap(commits_pivot, annot=True, fmt="g", cmap="Blues", linewidths=0.5)
        plt.title(
            "Total Commits per Module and Version", fontsize=16, fontweight="bold"
        )
        plt.xlabel("Odoo Version", fontsize=12)
        plt.ylabel("Module", fontsize=12)
        plt.xticks(rotation=45)
        plt.yticks(rotation=0)
        plt.tight_layout()
        commits_heatmap_path = output_path / "total_commits_heatmap.png"
        plt.savefig(commits_heatmap_path, dpi=300, bbox_inches="tight")
        print(f"Total commits heatmap saved to: {commits_heatmap_path}")
        plt.close()

        # Total lines heatmap
        lines_data = [{**item, "value": item["total_lines"]} for item in heatmap_data]
        lines_df = pd.DataFrame(lines_data)
        lines_pivot = lines_df.pivot(
            index="module", columns="version", values="value"
        ).fillna(0)
        lines_pivot = lines_pivot[version_order]

        plt.figure(figsize=(12, 8))
        sns.heatmap(lines_pivot, annot=True, fmt="g", cmap="Greens", linewidths=0.5)
        plt.title(
            "Total Line Changes per Module and Version", fontsize=16, fontweight="bold"
        )
        plt.xlabel("Odoo Version", fontsize=12)
        plt.ylabel("Module", fontsize=12)
        plt.xticks(rotation=45)
        plt.yticks(rotation=0)
        plt.tight_layout()
        lines_heatmap_path = output_path / "total_lines_heatmap.png"
        plt.savefig(lines_heatmap_path, dpi=300, bbox_inches="tight")
        print(f"Total lines heatmap saved to: {lines_heatmap_path}")
        plt.close()

    # Print summary
    print("\n" + "=" * 60)
    print("ANALYSIS SUMMARY")
    print("=" * 60)

    # Summary statistics
    df = pd.DataFrame(heatmap_data)
    print(f"Total modules analyzed: {df['module'].nunique()}")
    print(f"Total versions analyzed: {df['version'].nunique()}")
    print(f"Total local changes detected: {df['local_changes'].sum()}")
    print(f"Total commits analyzed: {df['total_commits'].sum()}")
    print(f"Total lines changed: {df['total_lines'].sum()}")

    print(f"\nResults saved to: {output_path.absolute()}")


if __name__ == "__main__":
    analyze()
