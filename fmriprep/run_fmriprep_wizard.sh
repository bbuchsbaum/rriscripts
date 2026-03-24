#!/bin/bash
set -euo pipefail

# Wrapper script to run fmriprep_launcher wizard with virtual environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Activate virtual environment if available
if [ -n "${VIRTUAL_ENV:-}" ]; then
    # Already in a venv, use it
    :
elif [ -f ~/fmriprep_env/bin/activate ]; then
    source ~/fmriprep_env/bin/activate
elif [ -f ~/myenv/bin/activate ]; then
    source ~/myenv/bin/activate
fi

# Check that questionary is available (optional but recommended)
if ! python3 -c "import questionary" 2>/dev/null; then
    echo "Note: 'questionary' package not found. The wizard will use basic prompts." >&2
    echo "For a better experience: pip install --user questionary" >&2
    echo "" >&2
fi

# Run the wizard using the script's own directory
exec python3 "$SCRIPT_DIR/fmriprep_launcher.py" wizard "$@"
