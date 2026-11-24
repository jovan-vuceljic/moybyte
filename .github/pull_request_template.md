## What and why

<!-- What this changes, and why. A sentence or two is plenty. -->

Addresses #

## Checklist

- [ ] It targets `dev` (GitHub offers `master`; switch the base).
- [ ] The branch has the current `dev` merged in: `git fetch origin && git merge origin/dev`, then push (from a fork, fetch and merge from the remote that points here). CI's "PR base" check fails until it does.
- [ ] `make preflight` (`tools/preflight.sh`) is green. It reaches: <!-- the host lane only / + the browser lane / + the board images -->
- [ ] Every commit is signed off (`git commit -s`, see CONTRIBUTING.md's DCO section).
- [ ] Docs changed with the behaviour and say what IS, not what changed; numbers go in an issue, not prose.
- [ ] Reaches firmware (`firmware/`, `device/`, `native/`): tried on <!-- which boards -->, or "not tried on a board".
