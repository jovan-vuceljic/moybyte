#!/usr/bin/env bash
# Does a pull request's head contain its base branch's current tip?
#
#   tools/pr_base_check.sh <base-branch> <base-sha> <head-sha>
#
# Exit 0 when <base-sha> is an ancestor of <head-sha>, 1 when it is not (with
# the command that fixes it), 2 when either commit is missing from this clone.
# .github/workflows/pr-base.yml runs it on every pull request with the base
# branch's tip as it is when the job runs, not as the PR's event recorded it,
# so a re-run after the base moves checks the new tip.
#
# A branch that is behind its base fails CI for changes it never made: the
# suite tests the PR's tree, whose derived artifacts and pins are the base's
# of whenever the branch was cut.
set -uo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <base-branch> <base-sha> <head-sha>" >&2
  exit 2
fi
BRANCH="$1"
BASE="$2"
HEAD="$3"

for c in "${BASE}" "${HEAD}"; do
  if ! git cat-file -e "${c}^{commit}" 2>/dev/null; then
    echo "pr_base_check: commit ${c} is not in this clone" >&2
    exit 2
  fi
done

if git merge-base --is-ancestor "${BASE}" "${HEAD}"; then
  echo "The branch contains ${BRANCH}'s tip (${BASE:0:12})."
  exit 0
fi

BEHIND="$(git rev-list --count "${HEAD}..${BASE}")"
MSG="This branch is ${BEHIND} commit(s) behind ${BRANCH} (tip ${BASE:0:12}). Merge it in and push: git fetch origin && git merge origin/${BRANCH} && git push"
if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
  echo "::error title=Branch is behind ${BRANCH}::${MSG}"
fi
cat <<EOF
${MSG}

CI tests this branch's own tree, so a branch that is behind ${BRANCH} fails
for changes it never made. From your branch, with origin being this
repository (in a fork, the remote that points here, often "upstream"):

    git fetch origin && git merge origin/${BRANCH}
    git push

Then this check and the rest of CI run again on the merged branch.
EOF
exit 1
