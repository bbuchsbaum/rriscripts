# Agent skills

Reusable skills for **Codex** and **Claude Code**. Each directory is a complete
skill with a `SKILL.md` entry point and supporting files loaded when needed.

| Skill | Use it for |
|---|---|
| [alliance-hpc](alliance-hpc/) | Plan, submit, monitor, and validate Alliance computing jobs on Trillium, Nibi, Fir, Rorqual, and Narval. |

Keep the canonical files here and link them into each agent's discovery
directory. The [installation instructions](alliance-hpc/README.md#installation)
support personal or repository scope and refuse to replace existing entries.
Copying a skill into this directory alone does not activate it in either agent.

Validate the Alliance skill without connecting to a cluster:

```bash
python3 skills/alliance-hpc/tests/test_skill.py
```
