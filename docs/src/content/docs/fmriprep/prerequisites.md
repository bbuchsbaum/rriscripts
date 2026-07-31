---
title: Prerequisites
description: The container image, FreeSurfer license, and TemplateFlow cache the launcher needs on the cluster.
---

You need three things on the cluster before the launcher can do useful work.
These are one-time setup steps and are usually shared across a lab.

All three exist because **compute nodes typically have no internet access**. Each
step is about getting something onto a filesystem the compute nodes can read,
while you are still on a login node.

:::note[Paths on this page are examples]
`def-piname` is a **placeholder for your own allocation**, not a real path. On
Digital Research Alliance of Canada clusters, allocations are named after the
PI's username — `def-<pi-username>` for a default allocation, `rrg-<pi-username>`
for a RAC allocation — so a real path looks more like
`/project/def-jsmith/shared/bin/`.

Substitute your own account everywhere it appears. To see which allocations you
belong to:

```bash
sacctmgr show associations user=$USER format=account%30
# or, on Alliance clusters:
groups
```

On a cluster that is not Alliance-run, the shared-storage path will follow a
different convention entirely — ask whoever administers it.
:::

## 1. An fMRIPrep container image

Run this on a **login node**:

```bash
# Pick and pin a version from https://hub.docker.com/r/nipreps/fmriprep/tags
# or https://fmriprep.org/en/latest/changes.html
VERSION=25.2.5

# Singularity (15-30 min):
singularity build fmriprep_${VERSION}.sif docker://nipreps/fmriprep:${VERSION}
# or with Apptainer:
apptainer pull docker://nipreps/fmriprep:${VERSION}

# Docker (local workstation):
docker pull nipreps/fmriprep:${VERSION}
```

Put the `.sif` somewhere lab members can share:

```bash
# Replace def-piname with your own allocation account.
mv fmriprep_${VERSION}.sif /project/def-piname/shared/bin/
```

You will set this in your config:

```ini
[defaults]
# Replace def-piname with your own allocation account.
container = /project/def-piname/shared/bin/fmriprep_25.2.5.sif
```

Replace `25.2.5` with the version your project has validated. Docker users can
skip the path if the image is already local — the launcher auto-discovers local
Docker images.

:::tip
Pin the version. fMRIPrep output changes between releases, and a dataset
preprocessed with two different versions is not one dataset.
:::

## 2. A FreeSurfer license

Get a free license at
<https://surfer.nmr.mgh.harvard.edu/registration.html> and save the returned
file as `license.txt`. fMRIPrep needs that file inside the container, so put it
on a filesystem visible to the compute nodes running your SLURM jobs.

For a lab-shared setup, use a shared project path:

```bash
# Replace def-piname with your own allocation account.
mkdir -p /project/def-piname/shared/freesurfer
cp license.txt /project/def-piname/shared/freesurfer/license.txt
chmod a+r /project/def-piname/shared/freesurfer/license.txt
```

Then set this once in your user-level config:

```ini
[defaults]
# Replace def-piname with your own allocation account.
fs_license = /project/def-piname/shared/freesurfer/license.txt
```

For a private per-user setup, use a path that compute jobs can read, such as
`$HOME/.licenses/freesurfer/license.txt` if home directories are mounted on
compute nodes, or `$SCRATCH/.licenses/freesurfer/license.txt` if they are not.

You can also set `FS_LICENSE=/path/to/license.txt`, but the config key is more
explicit and easier to share in project run notes.

## 3. A populated TemplateFlow cache

fMRIPrep downloads brain templates via
[TemplateFlow](https://www.templateflow.org/), which fails on air-gapped compute
nodes. Pre-populate the cache **on a login node**:

```bash
# Option A - use the templateflow Python API:
python -c "
import templateflow.api as tfa
tfa.get('MNI152NLin2009cAsym')
tfa.get('MNI152NLin6Asym')
tfa.get('fsaverage')
tfa.get('fsLR')
"

# Option B - copy from someone who already has it:
cp -r /project/shared/templateflow ~/.cache/templateflow
```

The launcher auto-binds your local cache into the container and sets
`TEMPLATEFLOW_HOME` inside it.

:::caution
The interactive wizards warn when the cache is missing or empty. `slurm-array`
does **not** — it assumes the path you pass is ready to use. A job that dies
minutes in with a TemplateFlow download error usually means this step was
skipped.
:::

## Confirming all three

```bash
fmriprep_launcher.py probe
```

`probe` lists the loaded config files and effective values, detects the
available runtime, and reports configured SIF images or local Docker fMRIPrep
images. Run it before generating a bundle — it is much cheaper than discovering
a missing license after the array job starts.
