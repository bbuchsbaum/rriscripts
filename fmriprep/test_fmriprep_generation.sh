#!/bin/bash

# Test script to generate proper fMRIPrep SLURM script

echo "Testing fMRIPrep launcher with proper paths..."

# Set environment variables
export TEMPLATEFLOW_HOME=/project/rrg-brad/shared/opt/templateflow

# Generate SLURM script with absolute paths
python fmriprep_launcher.py slurm-array \
  --bids /project/rrg-brad/shared/marie_video \
  --out /project/rrg-brad/shared/marie_video/derivatives/fmriprep \
  --work /scratch/brad/work \
  --subjects all \
  --runtime singularity \
  --container /project/rrg-brad/shared/bin/fmriprep_latest.sif \
  --fs-license /project/rrg-brad/shared/bin/license.txt \
  --templateflow-home /project/rrg-brad/shared/opt/templateflow \
  --nprocs 172 \
  --omp-threads 1 \
  --mem-mb 696044 \
  --skip-bids-validation \
  --fs-reconall \
  --use-syn-sdc \
  --partition compute \
  --time 12:00:00 \
  --account rrg-brad \
  --no-mem \
  --log-dir /scratch/brad/logs \
  --script-outdir /scratch/brad/fmriprep_job

echo "Script generated at /scratch/brad/fmriprep_job/fmriprep_array.sbatch"
echo "Check that all paths are absolute and TemplateFlow is included"