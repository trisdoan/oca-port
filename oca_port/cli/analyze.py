# Copyright 2023 Camptocamp SA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)

import os
import re
import click
import git
import json

from ..exceptions import RemoteBranchValueError
from ..utils.git import Branch
from ..utils.storage import InputStorage


def get_commit_range(repo_path, branch_start, branch_end, module=None):
    repo = git.Repo(repo_path)

    # Construct the revision range string for iter_commits
    # GitPython's iter_commits can take 'revA..revB'
    revision_range = f"{branch_start}..{branch_end}"

    # Use iter_commits with paths for module filtering
    # GitPython's iter_commits can take 'paths' argument directly.
    # Note: path filtering in iter_commits might be less precise than 'git log -- <path>'
    # in some edge cases with renames/copies across directories, but it's generally good.
    return repo.iter_commits(revision_range, paths=module)


def extract_pr_number(message):
    """
    Extracts a Pull Request number from a commit message.
    Looks for patterns like "Merge pull request #<PR_NUMBER>", "Closes #<PR_NUMBER>", etc.
    """
    # Pattern for "Merge pull request #<PR_NUMBER>"
    match_merge_pr = re.search(r"Merge pull request #(\d+)", message, re.IGNORECASE)
    if match_merge_pr:
        return int(match_merge_pr.group(1))

    # Pattern for "Closes #<PR_NUMBER>" or "Refs #<PR_NUMBER>"
    match_closes_refs = re.search(
        r"(?:Closes|Refs|Fixes)\s*#(\d+)", message, re.IGNORECASE
    )
    if match_closes_refs:
        return int(match_closes_refs.group(1))

    # Add more patterns if needed, e.g., for direct PR links or other conventions
    return None


def analyze_commits_gitpython(commits_generator):
    total_commits = 0
    total_added_lines = 0
    total_deleted_lines = 0
    categories = (
        {}
    )  # category -> {'commits': count, 'added_lines': count, 'deleted_lines': count}

    detailed_commits_info = []  # New list to store detailed commit data

    for commit in commits_generator:
        total_commits += 1

        current_commit_added = 0
        current_commit_deleted = 0

        # Sum lines changed from commit.stats.files (as confirmed working)
        for file_path, file_stats in commit.stats.files.items():
            current_commit_added += file_stats.get("insertions", 0)
            current_commit_deleted += file_stats.get("deletions", 0)

        total_added_lines += current_commit_added
        total_deleted_lines += current_commit_deleted

        # Categorize the commit message
        category = categorize_commit(commit.message)

        if category not in categories:
            categories[category] = {"commits": 0, "added_lines": 0, "deleted_lines": 0}
        categories[category]["commits"] += 1
        categories[category]["added_lines"] += current_commit_added
        categories[category]["deleted_lines"] += current_commit_deleted

        # Extract PR number
        pr_number = extract_pr_number(commit.message)

        # Store detailed commit information
        detailed_commits_info.append(
            {
                "hash": commit.hexsha,
                "short_hash": commit.hexsha[:7],
                "author_name": commit.author.name,
                "author_email": commit.author.email,
                "date": commit.authored_datetime.isoformat(),
                "message": commit.message.strip(),
                "pr_number": pr_number,
                "category": category,
                "added_lines": current_commit_added,
                "deleted_lines": current_commit_deleted,
                "total_line_changes": current_commit_added + current_commit_deleted,
            }
        )

    return {
        "total_commits": total_commits,
        "total_added_lines": total_added_lines,
        "total_deleted_lines": total_deleted_lines,
        "categories": categories,
        "detailed_commits": detailed_commits_info,  # Include the new detailed list
    }


def categorize_commit(message):
    """
    Categorizes a commit message based on predefined patterns.
    Returns the category name.
    """
    message_lower = message.lower()
    if re.search(r"\[fix\]\s*\S+", message_lower):
        return "fix"
    elif re.search(r"\[imp\]\s*\S+|\[ref\]\s*\S+", message_lower):
        # Specific module local change
        return "local change"
    elif re.search(r"\[imp\]|\[ref\]", message_lower) and (
        "core" in message_lower or "*" in message_lower
    ):
        # Global change (framework change)
        return "global change"
    elif "[i18n]" in message_lower:
        return "translations"
    # Add more categories as needed
    return "other"


@click.command()
@click.argument("source", required=True)
@click.argument("target", required=True)
@click.argument("module", required=False)
@click.option("--output-json", is_flag=True, help="Output results in JSON format.")
@click.option(
    "--repo-path",
    default=".",
    help="Path to the Git repository. Defaults to current directory.",
)
@click.option(
    "--output-file",
    type=click.Path(dir_okay=False, writable=True),
    help="Path to a file where the JSON output will be saved. Implies --output-json.",
)
def analyze(source, target, module, output_json, repo_path, output_file):
    click.echo(f"Analyzing commits from '{source}' to '{target}' in '{repo_path}'...")
    if module:
        click.echo(f"Filtering by module: '{module}'")

    commits_generator = get_commit_range(repo_path, source, target, module)
    all_commits = list(
        commits_generator
    )  # Convert generator to list to process multiple times if needed, or pass directly

    # Check if there are any commits to analyze
    if not all_commits:
        click.echo("No commits found in the specified range and module.", err=True)
        if output_json:
            click.echo(
                json.dumps(
                    {
                        "total_commits": 0,
                        "total_added_lines": 0,
                        "total_deleted_lines": 0,
                        "categories": {},
                        "detailed_commits": [],
                    },
                    indent=2,
                )
            )
        return

    results = analyze_commits_gitpython(all_commits)

    if output_file:
        # If output_file is specified, save to file regardless of output_json flag
        # but only if output_json is NOT explicitly set to False, as output_file implies output_json
        try:
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2)
            click.echo(f"JSON results saved successfully to '{output_file}'")
        except IOError as e:
            click.echo(f"Error saving JSON to file '{output_file}': {e}", err=True)
    elif (
        output_json
    ):  # Only print to console if output_file is NOT specified but output_json is true
        click.echo(json.dumps(results, indent=2))
    else:
        # Existing non-JSON output
        click.echo("\n--- Analysis Results ---")
        click.echo(f"Total commits: {results['total_commits']}")
        click.echo(f"Total lines added: {results['total_added_lines']}")
        click.echo(f"Total lines deleted: {results['total_deleted_lines']}")
        click.echo(
            f"Total line changes: {results['total_added_lines'] + results['total_deleted_lines']}"
        )
        click.echo("\n--- Commits and Line Changes per Category ---")
        for category, data in results["categories"].items():
            click.echo(f"Category: {category}")
            click.echo(f"  Commits: {data['commits']}")
            click.echo(f"  Lines added: {data['added_lines']}")
            click.echo(f"  Lines deleted: {data['deleted_lines']}")
            click.echo(
                f"  Total line changes: {data['added_lines'] + data['deleted_lines']}"
            )
            click.echo("-" * 20)

        click.echo("\n--- Top 10 Detailed Commits ---")
        for commit_info in results["detailed_commits"][:10]:
            pr_str = (
                f" (PR #{commit_info['pr_number']})" if commit_info["pr_number"] else ""
            )
            click.echo(
                f"  - {commit_info['short_hash']}{pr_str}: {commit_info['message'].splitlines()[0]} ({commit_info['total_line_changes']} lines)"
            )


if __name__ == "__main__":
    analyze()
