import subprocess
from .utils.misc import Output, bcolors as bc
import click
import tempfile
import os
from .utils import git as g


MESSAGE_TO_SQUASH = [
    "Added translation using Weblate",
    "Translated using Weblate",
    "Update translation files",
]
AUTHOR_EMAILS_TO_SQUASH = [
    "transbot@odoo-community.org",
    "noreply@weblate.org",
    "oca-git-bot@odoo-community.org",
    "oca+oca-travis@odoo-community.org",
    "oca-ci@odoo-community.org",
    "shopinvader-git-bot@shopinvader.com",
]


class SquashCommitBot(Output):

    def __init__(self, app) -> None:
        self.app = app
        self.skipped_commits = []

    def run(self):
        if self.app.non_interactive or self.app.dry_run:
            return False
        click.echo(
            click.style(
                "🚀 Starting reducing number of commits...",
                bold=True,
            ),
        )
        squashable_commits = self._get_squashable_commits()
        while len(squashable_commits) > 0:
            commit = squashable_commits.pop(0)
            result = self.squash(commit, squashable_commits)
            if not result:
                confirm = "Skip this commit?"
                if click.confirm(confirm):
                    self.skipped_commits.append(commit)
                    print(
                        f"\nSkipped {bc.OKCYAN}{commit.hexsha[:8]}{bc.ENDC} {commit.summary}\n"
                    )
            # update to get new SHAs
            squashable_commits = self._get_squashable_commits()
            print("\n")

    def _get_squashable_commits(self):
        commits = [
            g.Commit(commit, addons_path=self.app.addons_rootdir, cache=self.app.cache)
            for commit in self.app.repo.iter_commits(
                f"{self.app.target_version}...HEAD"
            )
        ]
        squashable_commits = [
            commit
            for commit in commits
            if self.is_squashable_commit(commit) and not self.is_skipped_commit(commit)
        ]
        return squashable_commits

    def squash(self, commit, squashable_commits):
        self._print(
            f"Squashing {bc.OKCYAN}{commit.hexsha[:9]}{bc.ENDC} {commit.summary}"
        )
        available_commits = [c for c in squashable_commits if c.hexsha != commit.hexsha]
        self._print(f"0) {bc.BOLD}Skip this commit{bc.END}")
        for idx, c in enumerate(available_commits):
            self._print(f"{idx + 1}) {bc.OKCYAN}{c.hexsha[:8]}{bc.ENDC} {c.summary}")
        choice = click.prompt("Select a commit to squash into:", type=int)
        if not choice:
            self.skipped_commits.append(commit)
            return False
        selected_commit = available_commits[choice - 1]
        reorder = selected_commit.__eq__(commit.parents[0])
        return self._squash(commit, selected_commit, reorder)

    def _squash(self, commit, target_commit, reorder=False):
        base_commit = target_commit.parents[0]
        confirm = "\n".join(
            [
                "\nCommits to Squash:",
                f"\t{bc.OKCYAN}{commit.hexsha[:9]}{bc.ENDC} {commit.summary}",
                f"\t{bc.OKCYAN}{target_commit.hexsha[:9]}{bc.ENDC} {target_commit.summary}\n",
            ]
        )
        if not click.confirm(confirm):
            return False
        editor_script = ""
        if reorder:
            with tempfile.NamedTemporaryFile(delete=False, mode="w") as temp_file:
                editor_script = temp_file.name
                temp_file.write(
                    f"""#!/bin/bash
                    todo_file=".git/rebase-merge/git-rebase-todo"
                    tmp_file="$todo_file.tmp"

                    # Copy todo_file to a temporary file
                    cp "$todo_file" "$tmp_file"
                    printf "%s\\n" "/^pick {commit.hexsha[:9]}/ m1" "wq" | ed -s "$tmp_file" 
                    printf "%s\\n" "/^pick {commit.hexsha[:9]} /s//squash {commit.hexsha[:9]} /" "wq" | ed -s "$tmp_file"
                    mv "$tmp_file" "$todo_file"
                    """
                )
            os.chmod(editor_script, 0o755)
            result = subprocess.run(
                f"GIT_SEQUENCE_EDITOR='{editor_script}' GIT_EDITOR=true git rebase -i {base_commit}",
                capture_output=True,
                shell=True,
            )
        else:
            command = f"GIT_SEQUENCE_EDITOR='sed -i \"s/^pick {commit.hexsha[:9]} /squash {commit.hexsha[:9]} /\"' GIT_EDITOR=true git rebase -i {base_commit}"
            result = subprocess.run(command, capture_output=True, shell=True)
        output = result.stdout.decode("utf-8")
        if editor_script:
            os.remove(editor_script)

        if "CONFLICT" in output:
            self._print(f"\n{bc.FAIL}ERROR: A conflict occurs{bc.ENDC}")
            self._print(
                "\n ⚠️You can't squash those commits together and they should be left as is"
            )
            self._abort_rebase()
            return False
        click.echo(
            click.style(
                "✨ Done! Successfully squashed.",
                fg="green",
                bold=True,
            )
        )
        return True

    def _abort_rebase(self):
        self._print()
        self.app.repo.git.rebase("--abort")

    def is_squashable_commit(self, commit):
        if any([msg in commit.summary for msg in MESSAGE_TO_SQUASH]):
            return True
        if commit.author_email in AUTHOR_EMAILS_TO_SQUASH:
            return True
        return False

    def is_skipped_commit(self, commit):
        return any(
            skipped_commit.__eq__(commit) for skipped_commit in self.skipped_commits
        )
