# Security follow-up — dependency cooldowns (2026-11-18)

## Starting point
Stacked on `security/installer-semver-ifs-20261111` (existing Draft PR #5). The older Semgrep run [42363767908](https://github.com/rahman-997/free-claude-code/actions/runs/42363767908) reported **15 findings** on a previous PR merge SHA, including absent Dependabot cooldowns and missing uv dependency cooldown.

## Implemented
1. Added explicit `cooldown.default-days: 7` to both ecosystems (`uv` and `github-actions`) in `.github/dependabot.yml`.
2. Added `exclude-newer = "7 days"` in `[tool.uv]` (the project requires uv 0.11.16 or newer).
3. Added `tests/test_dependency_cooldown.py`, pure-standard-library regression checks for both policies.

## Evidence and limits
- **PASS:** GitHub round-trip verification: two ecosystems have the expected seven-day cooldown; a single uv exclude-newer entry exists; test file committed.
- Current official GitHub documentation supports Dependabot cooldown `default-days` for GitHub Actions; current uv documentation supports relative-duration `exclude-newer`.
- **NOT EXECUTED:** the new Python regression test and full project CI on this branch. These require a dependency-complete Python 3.14 / uv environment.
- Only **2 categories** of the prior Semgrep findings are addressed by these configuration changes. Other security findings are intentionally not hidden, ignored, or declared fixed.
- Added update latency can delay adoption of brand-new fixes; urgent verified security releases should be handled via deliberate reviewed override, not blanket disabling of cooldown.
- No protected branch changes, merge, production deployment, credentials, API charges or manual paid CI.

## Pending
Run project CI and Semgrep against this branch. Then triage remaining findings separately by true security impact (do not turn 0o700 private credential directories into world-readable directories to satisfy an incorrect heuristic).
