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
        self._results = {
            "process": "analyze",
            "results": {
                "total_commits": 0,
                "total_line_changes": 0,
                "categories": {},
            },
        }

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
        result = {}
        categorized = defaultdict(list)
        line_changes_per_category = defaultdict(int)
        total_commits = 0
        total_line_changes = 0

        for _, commits in diff.commits_diff["addon"].items():
            for commit in commits:
                lines = self.get_commit_line_count(commit)
                if lines < self.min_lines:
                    continue
                category = self.categorize_commit(commit.summary)
                categorized[category].append(commit)
                line_changes_per_category[category] += lines
                total_line_changes += lines
                total_commits += 1
        result["total_commits"] = total_commits
        result["total_line_changes"] = total_line_changes
        result["categories"] = {
            cat: {
                "commits": len(commits),
                "line_changes": line_changes_per_category[cat],
            }
            for cat, commits in categorized.items()
        }
        self._results["results"] = result

    def print_changes(self):
        results = self._results["results"]
        self._print(f"\n{bc.HEADER}--- Analysis Results ---{bc.END}")
        self._print(
            f"{bc.BOLD}Total commits:{bc.END} {bc.OKBLUE}{results['total_commits']}{bc.END}"
        )
        self._print(
            f"{bc.BOLD}Total line changes:{bc.END} {bc.WARNING}{results['total_line_changes']}{bc.END}"
        )
        self._print(
            f"\n{bc.HEADER}--- Commits and Line Changes per Category ---{bc.END}"
        )
        for category, data in results["categories"].items():
            self._print(f"{bc.UNDERLINE}Category: {category}{bc.END}")
            self._print(f"  {bc.BOLD}Commits:{bc.END} {data['commits']}")
            self._print(
                f"  {bc.BOLD}Total line changes:{bc.END} {bc.WARNING}{data['line_changes'] }{bc.END}"
            )

    def run(self):
        self._print(
            f"Analyzing {bc.BOLD}{self.app.addon}{bc.END} "
            f"from {bc.BOLD}{self.app.source.ref}{bc.END} "
            f"to {bc.BOLD}{self.app.target.ref}{bc.END}"
        )
        self.compute_changes(self.branches_diff)
        self.print_changes()
        return True, self._results
