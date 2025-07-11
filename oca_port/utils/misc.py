# Copyright 2022 Camptocamp SA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)

import giturlparse
import json
import os
import re
from collections import defaultdict
from pathlib import Path

MANIFEST_NAMES = ("__manifest__.py", "__openerp__.py")


# Copy-pasted from OCA/maintainer-tools
def get_manifest_path(addon_dir):
    for manifest_name in MANIFEST_NAMES:
        manifest_path = os.path.join(addon_dir, manifest_name)
        if os.path.isfile(manifest_path):
            return manifest_path


class bcolors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[39m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ENDD = "\033[22m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"


def clean_text(text):
    """Clean text by removing patterns like '13.0', '[13.0]' or '[IMP]'."""
    return re.sub(r"\[.*\]|\d+\.\d+", "", text).strip()


def defaultdict_from_dict(d):
    nd = lambda: defaultdict(nd)  # noqa
    ni = nd()
    ni.update(d)
    return ni


class Output:
    """Mixin to handle the output of oca-port."""

    def _print(self, *args, **kwargs):
        """Like built-in 'print' method but check if oca-port is used in CLI."""
        app = self
        # FIXME: determine class
        if hasattr(self, "app"):
            app = self.app
        if app.cli and not app.output:
            print(*args, **kwargs)

    def _render_output(self, output, data):
        """Render the data with the expected format."""
        return getattr(self, f"_render_output_{output}")(data)

    def _render_output_json(self, data):
        """Render the data as JSON."""
        return json.dumps(data)


class SmartDict(dict):
    """Dotted notation dict."""

    def __getattr__(self, attrib):
        val = self.get(attrib)
        return self.__class__(val) if isinstance(val, dict) else val


REF_REGEX = r"((?P<remote>[\w-]+)/)?(?P<branch>.*)"


def parse_ref(ref):
    """Parse reference in the form '[remote/]branch'."""
    group = re.match(REF_REGEX, ref)
    return SmartDict(group.groupdict()) if group else None


def extract_ref_info(repo, kind, ref, remote=None):
    """Extract info from `ref`.

    >>> extract_ref_info(repo, "source", "origin/16.0")
    {'remote': 'origin', 'repo': 'server-tools', 'platform': 'github', 'branch': '16.0', 'kind': 'src', 'org': 'OCA'}
    """
    info = parse_ref(ref)
    if not info:
        raise ValueError(f"No valid {kind}")
    info["ref"] = ref
    info["kind"] = kind
    info["remote"] = info["remote"] or remote
    info.update({"org": None, "platform": None})
    if info["remote"]:
        remote_url = repo.remotes[info["remote"]].url
        p = giturlparse.parse(remote_url)
        try:
            info["repo"] = p.repo
        except AttributeError:
            pass
        info["platform"] = p.platform
        info["org"] = p.owner
    else:
        # Fallback on 'origin' to grab info like platform, and repository name
        if "origin" in repo.remotes:
            remote_url = repo.remotes["origin"].url
            p = giturlparse.parse(remote_url)
            try:
                info["repo"] = p.repo
            except AttributeError:
                pass
            info["platform"] = p.platform
            info["org"] = p.owner
    return info


def pr_ref_from_url(url):
    if not url:
        return ""
    # url like 'https://github.com/OCA/edi/pull/371'
    org, repo, __, nr = url.split("/")[3:]
    return f"{org}/{repo}#{nr}"


def list_versions_between(source, target):
    source_info = parse_ref(source)
    source_branch = None
    if source_info:
        source_branch = source_info["branch"]

    target_info = parse_ref(target)
    target_branch = None
    if target_info:
        target_branch = target_info["branch"]

    def parse_version(version_str):
        major, minor = map(int, version_str.split("."))
        return major * 10 + minor  # Convert 15.0 to 150, 16.0 to 160

    def format_version(version_int):
        major = version_int // 10
        minor = version_int % 10
        return f"{major}.{minor}"

    source_int = parse_version(source_branch)
    target_int = parse_version(target_branch)
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


def find_module_path(repo_path: Path, module_name: str):
    repo_path = Path(repo_path)
    for path in repo_path.glob(f"**/{module_name}"):
        if path.is_dir():
            if (path / "__manifest__.py").exists() or (
                path / "__openerp__.py"
            ).exists():
                return str(path)

    error = f"Module {module_name} does not exist on {repo_path}"
    raise ValueError(error)
