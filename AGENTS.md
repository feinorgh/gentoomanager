<!--# cspell: ignore SSOT CMDB -->
# AGENTS.md

Ensure that all practices and instructions described by
https://raw.githubusercontent.com/ansible/ansible-creator/refs/heads/main/docs/agents.md
are followed.

## CI Verification

After every `git push`, **always** check that the GitHub Actions workflows pass
before considering a task complete.

1. List recent workflow runs and wait for them to finish:
   ```
   gh run list --branch main --limit 5
   gh run watch <run-id>
   ```
2. If any run fails, retrieve the logs and fix the root cause:
   ```
   gh run view <run-id> --log-failed
   ```
3. Do not mark a task done until all CI jobs show a green status (`completed` /
   `success`).  The gate job is named **all_green** — it must pass.
