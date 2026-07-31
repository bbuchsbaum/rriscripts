---
title: cmd_expand syntax
description: Turning bracket expressions like [1..100] and [file:subjects.txt] into concrete command lines.
---

`cmd_expand.sh` takes a template command containing bracket expressions and
prints one concrete command line per combination. It does not submit anything —
pipe it into `send_slurm.sh`, redirect it to a file, or let `batch_exec.sh` call
it for you.

```bash
cmd_expand.sh Rscript run.R --sub [1..3]
```

```text
Rscript run.R --sub 1
Rscript run.R --sub 2
Rscript run.R --sub 3
```

## Value syntax

Values inside `[]` are expanded:

| Syntax | Example | Expands to |
|---|---|---|
| Comma list | `[a,b,c]` | `a`, `b`, `c` |
| Integer range | `[1..5]` or `[1:5]` | `1`, `2`, `3`, `4`, `5` |
| File lines | `[file:subjects.txt]` | One value per nonblank line, trimmed |
| CSV column | `[df:subject:data.csv]` | Values from column `subject` |
| Glob | `[glob:data/*.nii]` | Matching file paths |

## Cartesian product (default)

With more than one bracket, every combination is produced:

```bash
cmd_expand.sh prog --sub [1,2] --roi [V1,MT]
```

```text
prog --sub 1 --roi V1
prog --sub 1 --roi MT
prog --sub 2 --roi V1
prog --sub 2 --roi MT
```

This is what you want for a parameter sweep. Note that the count multiplies
fast — `[1..100]` crossed with `[lasso,ridge]` is 200 commands.

## Linked mode

`--link` zips the expansions by position instead of crossing them. Shorter lists
repeat their last value:

```bash
cmd_expand.sh --link prog --sub [1,2,3] --roi [V1,MT]
```

```text
prog --sub 1 --roi V1
prog --sub 2 --roi MT
prog --sub 3 --roi MT
```

Use this when the values correspond to each other — subject 1 goes with its own
session, not with every session.

:::caution
The repeat-last-value rule means a length mismatch is silently absorbed rather
than reported. Check the output when your lists should be the same length.
:::

## Output controls

| Flag | Effect |
|---|---|
| `--quote` | Shell-quote expanded tokens before joining |
| `--json` | Emit the commands as a JSON array of strings |

`--quote` matters whenever expanded values can contain spaces or shell
metacharacters — filenames from `[glob:…]` and free-text CSV columns especially:

```bash
cmd_expand.sh --quote prog --input [file:subjects.txt] --atlas [AAL,Schaefer]
```

`--json` is useful when another tool consumes the command list:

```bash
cmd_expand.sh --json prog --sub [1..3] | jq length
```

## Feeding the result to SLURM

Generate, review, then submit — the safest pattern for a large sweep:

```bash
cmd_expand.sh Rscript run.R --sub [1..50] --roi [V1,MT,FFA] > commands.txt
wc -l commands.txt
head commands.txt
bexec.sh --file commands.txt --nodes 4 --jobs 10 --ncpus 40 --time 3
```

Or pipe straight through:

```bash
cmd_expand.sh prog [1..50] | send_slurm.sh --time 2 --ncpus 8
```

Or let `batch_exec.sh` do the expansion itself — it calls `cmd_expand.sh`
internally and passes `--link`/`--quote` through:

```bash
batch_exec.sh --time 2 --nodes 5 --ncpus 40 --jobs 40 -- \
    Rscript analyze.R --sub [1..100] --method [lasso,ridge]
```
