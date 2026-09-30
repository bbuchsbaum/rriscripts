# alliance-hpc

A portable Codex / Claude Code skill for productive, policy-aware data analysis on **Trillium, Nibi, Fir, Rorqual, and Narval**. Audited 2026-09-21.

`SKILL.md` is the small operational core. Detailed sources, cluster differences, submission recipes, and the qexec audit are read only when needed. The package does not install software, change SSH configuration, submit jobs, or modify qexec merely by being loaded.

## Installation

The canonical copy is `skills/alliance-hpc/` in this repository. Link both agents
to it so updates cannot drift between copies. Inspect the files first, then run
the following **from this skill directory** (`cd skills/alliance-hpc` from the
repository root). It refuses to replace any existing entry, including dangling
symlinks. Keep the checkout at this path while the links are in use.

```bash
(
  set -eu
  skill_dir="$(pwd -P)"
  test -f "$skill_dir/SKILL.md"
  codex_link="$HOME/.agents/skills/alliance-hpc"
  claude_link="$HOME/.claude/skills/alliance-hpc"
  for link in "$codex_link" "$claude_link"; do
    if [ -e "$link" ] || [ -L "$link" ]; then
      printf 'Already exists; inspect before updating: %s\n' "$link" >&2
      exit 1
    fi
  done
  mkdir -p "$HOME/.agents/skills" "$HOME/.claude/skills"
  ln -s "$skill_dir" "$codex_link"
  ln -s "$skill_dir" "$claude_link"
)
```

For **repository scope instead**, run this from the repository root:

```bash
(
  set -eu
  test -f skills/alliance-hpc/SKILL.md
  for link in .agents/skills/alliance-hpc .claude/skills/alliance-hpc; do
    if [ -e "$link" ] || [ -L "$link" ]; then
      printf 'Already exists; inspect before updating: %s\n' "$link" >&2
      exit 1
    fi
  done
  mkdir -p .agents/skills .claude/skills
  ln -s ../../skills/alliance-hpc .agents/skills/alliance-hpc
  ln -s ../../skills/alliance-hpc .claude/skills/alliance-hpc
)
```

Choose one scope. Avoid duplicate same-name installations that point at different
versions. These are local **Codex and Claude Code** instructions; browser/cloud
sessions do not automatically read this computer's home directory. Both products
document these discovery paths and symlink support:
[Codex](https://developers.openai.com/codex/skills/) ·
[Claude Code](https://code.claude.com/docs/en/skills).

Invoke in Codex with `$alliance-hpc` or in Claude Code with `/alliance-hpc`, or ask a matching task. For example:

> Use alliance-hpc to prepare a 120-subject R analysis. Compare legal placements on Trillium, Nibi, Fir, Rorqual, and Narval using current access, cached data, and representative timings. Dry-run first; do not submit until the pilot plan is reviewed.

The user prompt governs authorization; the skill does not imply permission to run that campaign.

## Included

| File | Purpose |
|---|---|
| `SKILL.md` | Compact operating contract and routing |
| `references/systems.md` | Five-cluster map, Trillium GPU branch, drift checks |
| `references/submission.md` | Native CPU, array, packed-work, dependency, GPU/MPI recipes |
| `references/operations.md` | Storage/S3 caches, offline environments, queue diagnosis, recovery |
| `references/qexec.md` | Audit of the actual Bash wrapper and helper behavior |
| `references/sources.md` | Primary sources, hashes, conflicts, and verification gaps |
| `scripts/probe.sh` | Bounded read-only cluster/account/resource/storage snapshot |
| `scripts/array-task.sh` | Safe data-only array manifest dispatch |
| `templates/cpu.sbatch` | One-node / one-task launcher with explicit environment and thread budget |
| `tests/test_skill.py` | Local syntax, safety and mocked-execution tests |
| `tests/VALIDATION.md` | Test results and untested boundaries |

## Use the probe

Run on an authorized target login host, not on the laptop. `WORKDIR` must already exist. It does not probe external network access, change files, submit/cancel jobs, or expose the full environment. It prints diagnostics only. Some command fields are version-dependent; failures and truncated output return code 2 (incomplete evidence). Each query has a time limit; displayed output is capped at 120 lines per query.

```bash
# After installing/copying the inspected probe onto the target host:
umask 077
bash /absolute/path/alliance-hpc/scripts/probe.sh /absolute/workdir \
  > /private/path/cluster-profile.txt
```

Capture the profile on durable authorized storage, outside the dataset's public outputs. An optional `ALLIANCE_PROBE_QOS=verified-qos` scopes one QOS query. Do not query every cluster repeatedly or paste full snapshots into every agent turn; retain a short selected-profile summary. The snapshot cannot establish all inherited policy limits, scratch retention, robot authorization, or compute-node mounts.

## Validation and honesty

From this directory, run `python3 tests/test_skill.py` locally. The checks require
Bash 3.2+, Python 3.9+, and GNU `timeout` on `PATH` (including on macOS for probe
tests). They do not require Slurm and never submit a job. Tests establish helper
behavior under mocks, not acceptance by a live Alliance scheduler. See the
[validation report](tests/VALIDATION.md) for the checks and remaining boundaries.

Verify the bundle inventory with `shasum -a 256 -c SHA256SUMS`. Regenerate that
inventory when changing bundle files; it covers every distributed file except
itself.

The Alliance wiki blocked full-page retrieval during authoring. Accessible operator pages, institutional operational documentation, upstream Slurm manuals, and the exact qexec source were inspected. Facts based only on indexing or software configuration are labelled. Current account permissions, walltime/QOS limits, quotas/purge rules, GPU slices, and site-specific automation access **must still be verified on the target**. The skill is designed to perform that verification rather than quietly reuse obsolete constants.
