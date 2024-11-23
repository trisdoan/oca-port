import subprocess
from .utils.misc import Output, bcolors as bc
import git
import click
import tempfile
import os
import re


class SquashBotCommit(Output):

    def __init__(self, app, squashable_commits) -> None:
        self.app = app
        self.squashable_commits = {}
        for commit in squashable_commits:
            self.squashable_commits[commit.hexsha[:9]] = commit

    def run(self):
        if self.app.non_interactive or self.app.dry_run:
            return False
        click.echo(
            click.style(
                "Starting reducing number of commits...",
                bold=True,
            ),
        )
        for hexsha, commit in self.squashable_commits.copy().items():
            is_squashed = self._squash(
                self.squashable_commits[hexsha],
                self.squashable_commits[hexsha].parents[0],
            )
            if not is_squashed:
                available_commits = [
                    c
                    for c in self.squashable_commits
                    if c != commit and c not in commit.parents
                ]
                for idx, c in enumerate(available_commits):
                    self._print(
                        f"{idx + 1}) {bc.OKCYAN}{c.hexsha[:8]}{bc.ENDC} {c.summary}"
                    )
                # TODO: option to skip this commit
                choice = click.prompt("Select a commit to squash into:", type=int)
                selected_commit = available_commits[choice - 1]
                is_squashed = self._squash(commit, selected_commit, reorder=True)
                continue
        return True

    def _squash(self, commit, parent_commit, reorder=False):
        # TODO: conflict handle: break the flow and allow user to handle conflict or skip
        confirm = "\n".join(
            [
                "\nCommits to Squash:",
                f"\t{bc.OKCYAN}{commit.hexsha[:8]}{bc.ENDC} {commit.summary}",
                f"\t{bc.OKCYAN}{parent_commit.hexsha[:8]}{bc.ENDC} {parent_commit.summary}\n",
            ]
        )
        if not click.confirm(confirm):
            # TODO: in case of not squashing into parent, how to revert if accidentally chose wrong index
            return False
        base_commit = parent_commit.parents[0].hexsha
        # TODO: change variable_name
        if reorder:
            # TODO: understand module NamedTemporaryFile
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
            subprocess.run(
                f"GIT_SEQUENCE_EDITOR='{editor_script}' GIT_EDITOR=true git rebase -i {base_commit}",
                shell=True,
            )
            os.remove(editor_script)
        # FIXME: update new hexsha of squashed commit
        # otherwise every 2nd time running does not take effect
        else:
            # squash to its parent
            base_commit = parent_commit.parents[0].hexsha
            command = f"GIT_SEQUENCE_EDITOR='sed -i \"s/^pick {commit.hexsha[:9]} /squash {commit.hexsha[:9]} /\"' GIT_EDITOR=true git rebase -i {base_commit}"
            try:
                is_needed_update = self.squashable_commits.get(
                    parent_commit.hexsha[:9], False
                )
                subprocess.run(command, shell=True)
                del self.squashable_commits[commit.hexsha[:9]]
                if is_needed_update:
                    with tempfile.NamedTemporaryFile(
                        delete=False, mode="w"
                    ) as temp_file:
                        editor_script = temp_file.name
                        temp_file.write(
                            """#!/bin/bash
                            todo_file=".git/rebase-merge/git-rebase-todo"
                            awk '/^pick / {print $2;exit}' "$todo_file" 
                            """
                        )
                    os.chmod(editor_script, 0o755)
                    new_commit = subprocess.run(
                        f"GIT_SEQUENCE_EDITOR='{editor_script}' GIT_EDITOR=true git rebase -i {base_commit}",
                        shell=True,
                        capture_output=True,
                    ).stdout
                    # output: b'2e6fb2a69\n'
                    new_commit_obj = [
                        commit
                        for commit in self.app.repo.iter_commits(
                            f"{self.app.target_version}...HEAD"
                        )
                        if commit.hexsha[:9] == new_commit
                    ]
                    print("new_commit_obj", new_commit_obj)
                    self.squashable_commits[is_needed_update] = new_commit_obj

            except git.exc.GitCommandError as exc:
                return
        return True

    def _abort_rebase(self):
        self._print()
        self.app.repo.git.rebase("--abort")
