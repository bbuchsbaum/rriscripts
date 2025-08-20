#!/bin/bash
# Wrapper script to run fmriprep_launcher with virtual environment

# Activate virtual environment if it exists
if [ -f ~/fmriprep_env/bin/activate ]; then
    source ~/fmriprep_env/bin/activate
elif [ -f ~/myenv/bin/activate ]; then
    source ~/myenv/bin/activate
fi

# Run the wizard
python fmriprep_launcher.py wizard "$@"