# Copyright 2025 Camptocamp
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)

import re
from collections import defaultdict
from oca_port.port_addon_pr import BranchesDiff

from .utils.misc import Output, bcolors as bc


class AnalyzeNativeChanges(Output):

    # TODO: option to only get specific commit, see https://git-scm.com/docs/git-rev-list
    def __init__(self, app, min_lines=0):
        self.app = app
        self.branches_diff = BranchesDiff(self.app)
        self.min_lines = min_lines
        self._results = {"process": "analyze"}

    def get_commit_line_count(self, commit):
        # lines = total number of lines changed as int, or deletions + insertions
        return commit.raw_commit.stats.total.get("lines", 0)

    # TODO: to be improved based on experienced
    def categorize_commit(self, message):
        message_lower = message.lower()
        if re.search(r"\[fix\]\s*\S+", message_lower):
            return "fix"
        elif re.search(r"\[imp\]\s*\S+|\[ref\]\s*\S+", message_lower):
            return "local change"
        elif re.search(r"\[imp\]|\[ref\]", message_lower) and (
            "core" in message_lower or "*" in message_lower
        ):
            return "global change"
        elif "[i18n]" in message_lower:
            return "translations"
        return "other"

    def compute_changes(self, diff):
        category_commits = defaultdict(list)
        category_lines = defaultdict(int)
        total_commits = 0
        total_lines = 0

        for commit in diff.commits_diff:
            line_count = self.get_commit_line_count(commit)
            if line_count < self.min_lines:
                continue

            category = self.categorize_commit(commit.summary)

            category_commits[category].append(
                {
                    "hexsha": commit.hexsha,
                    "summary": commit.summary,
                }
            )
            category_lines[category] += line_count
            total_commits += 1
            total_lines += line_count
        categories_summary = {
            category: {
                "commits": len(commits),
                "line_changes": category_lines[category],
                "commit_details": commits,
            }
            for category, commits in category_commits.items()
        }

        self._results["results"] = {
            "total_commits": total_commits,
            "total_line_changes": total_lines,
            "categories": categories_summary,
        }

    def print_changes(self):
        results = self._results["results"]
        lines = []

        lines.append(f"\n{bc.HEADER}--- Analysis Result ---{bc.END}")
        lines.append(
            f"{bc.BOLD}Total commits:{bc.END} {bc.OKBLUE}{results['total_commits']}{bc.END}"
        )
        lines.append(
            f"{bc.BOLD}Total line changes:{bc.END} {bc.WARNING}{results['total_line_changes']}{bc.END}"
        )
        lines.append(f"\n{bc.HEADER}--- Breakdown by Category ---{bc.END}")

        for idx, (category, data) in enumerate(results["categories"].items(), 1):
            lines.append(f"\n{idx}) {bc.UNDERLINE}Category: {category}{bc.END}")
            lines.append(
                f"   {bc.BOLD}Commits:{bc.END} {bc.OKBLUE}{data['commits']}{bc.END}"
            )
            lines.append(
                f"   {bc.BOLD}Total line changes:{bc.END} {bc.WARNING}{data['line_changes']}{bc.END}"
            )
            if category == "translations":
                continue
            lines.append(f"   {bc.BOLD}Commit details:{bc.END}")

            for commit in data["commit_details"]:
                summary = commit["summary"].splitlines()[0]
                hexsha = commit["hexsha"]
                lines.append(f"     - {bc.DIM}{hexsha}: {summary}{bc.ENDD}")

        self._print("\n".join(lines))

    def run(self):
        self.compute_changes(self.branches_diff)
        if self.app.output:
            return True, self._render_output(self.app.output, self._results)
        else:
            self.print_changes()
            return True, None
