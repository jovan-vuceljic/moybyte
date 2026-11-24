"""tools/pr_base_check.sh on a branch behind its base and on one that has the
base merged in, and the workflow that runs it on every pull request."""

import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "tools", "pr_base_check.sh")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "pr-base.yml")
MERGE = "git fetch origin && git merge origin/dev"


def _git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(k, None)
    return subprocess.run(["git", "-C", repo, *args], check=True, env=env,
                          capture_output=True, text=True).stdout.strip()


def _commit(repo, name):
    with open(os.path.join(repo, name), "w") as f:
        f.write(name)
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", name)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    r = str(tmp_path)
    _git(r, "init", "-q", "-b", "dev")
    _commit(r, "a")
    _git(r, "checkout", "-q", "-b", "feature")
    _commit(r, "feature")
    _git(r, "checkout", "-q", "dev")
    _commit(r, "b")
    _commit(r, "c")
    return r


def _check(repo, base, head):
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"}
    return subprocess.run(["bash", SCRIPT, "dev", base, head], cwd=repo,
                          env=env, capture_output=True, text=True)


def test_a_branch_behind_its_base_fails_with_the_merge_command(repo):
    res = _check(repo, _git(repo, "rev-parse", "dev"),
                 _git(repo, "rev-parse", "feature"))
    assert res.returncode == 1
    assert "2 commit(s) behind dev" in res.stdout
    assert MERGE in res.stdout


def test_a_branch_with_its_base_merged_in_passes(repo):
    _git(repo, "checkout", "-q", "feature")
    _git(repo, "merge", "-q", "--no-edit", "dev")
    res = _check(repo, _git(repo, "rev-parse", "dev"),
                 _git(repo, "rev-parse", "feature"))
    assert res.returncode == 0, res.stdout + res.stderr


def test_a_branch_cut_from_the_tip_passes(repo):
    _git(repo, "checkout", "-q", "-b", "fresh")
    head = _commit(repo, "fresh")
    assert _check(repo, _git(repo, "rev-parse", "dev"), head).returncode == 0


def test_a_commit_missing_from_the_clone_is_an_error_not_a_verdict(repo):
    res = _check(repo, "0" * 40, _git(repo, "rev-parse", "feature"))
    assert res.returncode == 2


def test_the_workflow_runs_the_script_on_every_pr_and_rechecks_on_a_base_push():
    with open(WORKFLOW) as f:
        wf = f.read()
    assert "pull_request:" in wf and "tools/pr_base_check.sh" in wf
    # the check reads the base's tip when it runs, so a re-run sees a moved base
    assert 'git rev-parse "origin/$BRANCH"' in wf
    assert "fetch-depth: 0" in wf
    assert "gh run rerun" in wf and "--workflow pr-base.yml" in wf


@pytest.mark.parametrize("rel", ["CONTRIBUTING.md",
                                 ".github/pull_request_template.md"])
def test_the_contributor_docs_give_the_command_the_check_prints(rel):
    with open(os.path.join(ROOT, rel)) as f:
        assert MERGE in f.read()
