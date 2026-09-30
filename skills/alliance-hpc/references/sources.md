# Source register and verification boundaries

Audit date: **2026-09-21**. This package is an operational synthesis, not Alliance policy. No cluster login, live Slurm allocation, or scientific workload was executed during authoring. Shell helpers receive local syntax/mock tests, documented in `tests/VALIDATION.md`.

**Evidence labels:** FULL = page/source body read; INDEX = indexed excerpt only; CONFIG = primary software implementation, not site authority. The central Alliance wiki returned an Anubis access-denied page to this research environment. Its exact current walltime, queue limits, purge rules, and account-specific eligibility could not be comprehensively verified. The skill therefore requires targeted live verification rather than inventing numbers.

## Repository review, 2026-09-21

The original archive inventory was checked before import into
`rriscripts/skills/alliance-hpc`. The review independently rechecked SciNet's
Trillium hardware and quickstart, Mila's cluster guide, nf-core's configuration,
and the official Codex/Claude Code skill discovery and symlink documentation.
The three qexec sources below were read locally and their Git blob hashes match
the original audit exactly. Other source labels retain the supplied bundle's
authoring evidence; they do not imply every page was retrieved again.

The central Alliance wiki still returned an access-denied page. Current
entitlements and site limits remain verification targets. Local fixes make
submission stop on preflight failure and make truncated probe output return
incomplete-evidence status. Tests and their scope are in the
[validation report](../tests/VALIDATION.md).

## Cluster and service sources

- **S1 — FULL, SciNet operator:** [Trillium hardware](https://scinethpc.ca/trillium/) and [Trillium Quickstart](https://docs.scinet.utoronto.ca/index.php/Trillium_Quickstart). The hardware page prints **196** CPU cores but its own arithmetic gives 235,008 / 1,224 = **192**; the quickstart explicitly says **192**. We use 192 and require live confirmation. Do not propagate the typo or stale total node counts.
- **S1b — FULL, SciNet operator:** [Restricted Neptune nodes](https://docs.scinet.utoronto.ca/index.php/Trillium_Neptune_Nodes), corroborating 192 regular Trillium cores and distinguishing restricted 40-core nodes.
- **S2 — FULL, institutional operational guide:** [Mila DRAC clusters](https://docs.mila.quebec/technical_reference/clusters/drac/), including the 2026–27 table. Used narrowly for operational differences, GPU starting points, and egress. Mila-specific allocation and project-storage rules are **not** generalized to all Alliance users. Egress/access details require local confirmation.
- **S3 — CONFIG:** [nf-core Alliance configuration](https://nf-co.re/configs/alliance_canada/), modified 2026-04-17. Used only as a baseline CPU profile cross-check. Its resource caps, queue-size settings, and submit rate are software defaults, **not site policy**.
- **S4 — FULL / INDEX, SHARCNET:** [Nibi Open OnDemand webinar description](https://helpwiki.sharcnet.ca/wiki/Webinar_2025_Running_Engineering_Related_Packages_Interactively_on_Nibi) (FULL); [AMD GPUs/APUs seminar](https://www.youtube.com/watch?v=IassGkLKTfA), 2026-08-07 (INDEX only). The latter advertises Nibi MI300As; neither full presentation nor entitlement/GRES was verified.
- **S5 — FULL, SFU operator:** [Fir launch](https://www.sfu.ca/sfunews/stories/2025/09/canada-s-fastest-academic-supercomputer-is-now-online-at-sfu-aft.html) and [Fir access registration](https://sfu.teamdynamix.com/TDClient/255/ITServices/KB/Article/3916/Register-For-Access-to-Fir). These establish replacement/access context, not partition policy.
- **S6 — FULL, operator portals:** [Rorqual](https://metrix.rorqual.calculquebec.ca/), [Narval](https://portail.narval.calculquebec.ca/), [Nibi](https://portal.nibi.sharcnet.ca/). Scheduler/transfer subpages read. Charts may need authenticated/browser access; no live utilization number is asserted here.
- **S7 — INDEX / verification targets:** [Alliance Globus](https://docs.alliancecan.ca/wiki/Globus), [Fir](https://docs.alliancecan.ca/wiki/Fir), [Alliance Fir service](https://www.alliancecan.ca/services/compute/fir-installation-in-progress). Indexed collection names include both legacy Cedar and Fir labels; the skill intentionally does not hard-code a collection UUID/name.
- **S7a — INDEX:** [Automation with multifactor authentication](https://docs.alliancecan.ca/wiki/Automation_in_the_context_of_multifactor_authentication). Indexed robot names: `robot.fir.alliancecan.ca`, `robot.nibi.alliancecan.ca`, `robot.rorqual.alliancecan.ca`, `robot.narval.alliancecan.ca`. Registration and command restrictions must be read before use; this is not approval to connect.

## Slurm primary references — FULL

- **S8:** [sacctmgr](https://slurm.schedmd.com/sacctmgr.html): associations, account/QOS fields, read commands.
- **S9:** [sinfo](https://slurm.schedmd.com/sinfo.html): resource/topology/partition reporting and units.
- **S10:** [Resource-limit hierarchy](https://slurm.schedmd.com/resource_limits.html).
- **S11:** [sbatch](https://slurm.schedmd.com/sbatch.html): submission, resource flags, environment, test-only, receipt and dependencies.
- **S12:** [srun](https://slurm.schedmd.com/srun.html): job steps, task layout, allocation/launch distinction.
- **S13:** [Job arrays](https://slurm.schedmd.com/job_array.html): element IDs, throttles, dependencies and logs.
- **S14:** [squeue](https://slurm.schedmd.com/squeue.html): states and estimated starts.
- **S15:** [Scheduling/backfill](https://slurm.schedmd.com/sched_config.html).
- **S16:** [Multifactor priority](https://slurm.schedmd.com/priority_multifactor.html).
- **S17:** [sacct](https://slurm.schedmd.com/sacct.html): step accounting, metrics and exit status.
- **S18:** [Job reason codes](https://slurm.schedmd.com/job_reason_codes.html).
- **S19:** [scontrol](https://slurm.schedmd.com/scontrol.html): selected configuration/job inspection.

These are current upstream manuals, not proof that each cluster runs the newest Slurm. Check installed `--help`/manuals when a command or field differs. Unsupported diagnostic fields are reported as gaps, not “unlimited.”

## Qexec source audit

FULL source read through GitHub during authoring, then rechecked against this
repository during import. No qexec implementation changes were made.

- **Q1:** [qexec.sh at its latest retrieved modifying commit](https://github.com/bbuchsbaum/rriscripts/blob/25fcd3b05dbb1606039a26362ef0342031afbcc9/qexec/qexec.sh). Blob `85aaa67554a1941e06bfdd4b66716779a3c11e0c`.
- **Q2:** [command_distributor.sh](https://github.com/bbuchsbaum/rriscripts/blob/main/qexec/command_distributor.sh). Retrieved blob `9e21a54f18fe00b04168ccc3bdcd824dcf99c99a`.
- **Q3:** [slurm_job_monitor.sh](https://github.com/bbuchsbaum/rriscripts/blob/main/qexec/slurm_job_monitor.sh). Retrieved blob `152a2edf5323795c0549cbd85779a733d5e8ef44`.

`main` links can change; the recorded blob hashes identify what was inspected. Audit the installed source again if its hash differs.

## Installation format — FULL official documentation

[Codex skills](https://developers.openai.com/codex/skills/) and [Claude Code skills](https://code.claude.com/docs/en/skills). Both support `SKILL.md` and referenced files, and both document symlinked local skill directories. This package uses only common `name`/`description` frontmatter, without vendor-specific hooks or automatic shell execution.

## Policy refresh targets

[Trillium Quickstart](https://docs.alliancecan.ca/wiki/Trillium_Quickstart), [Nibi](https://docs.alliancecan.ca/wiki/Nibi), [Fir](https://docs.alliancecan.ca/wiki/Fir), [Rorqual](https://docs.alliancecan.ca/wiki/Rorqual), [Narval](https://docs.alliancecan.ca/wiki/Narval), [Running jobs](https://docs.alliancecan.ca/wiki/Running_jobs), [Storage](https://docs.alliancecan.ca/wiki/Storage_and_file_management), [Service status](https://status.alliancecan.ca/).

The central wiki pages are authoritative targets, **not pages whose complete contents were accessible in this audit**. Preserve policy URLs, checked date, and selected configuration in a private campaign profile. Update only affected facts; do not inflate the core with incident histories or exhaustive module/node inventories.
