#!/bin/bash
set -euo pipefail

# Install fmriprep launcher scripts to ~/bin (or a custom directory).
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/fmriprep/install.sh | bash
#   curl -fsSL ... | bash -s -- --prefix /opt/bin

REPO="bbuchsbaum/rriscripts"
BRANCH="main"
PREFIX="${HOME}/bin"

SCRIPTS=(
    fmriprep_launcher.py
    fmriprep_backend.py
    fmriprep_shared.py
    fmriprep_tui_autocomplete.py
    fmriprep_gui_tk.py
    run_fmriprep_wizard.sh
    slurm_batched_template.sh
    fmriprep_config_example.ini
    fmriprep_project_example.ini
)

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix) PREFIX="$2"; shift 2 ;;
        --prefix=*) PREFIX="${1#--prefix=}"; shift ;;
        -h|--help)
            echo "Usage: install.sh [--prefix DIR]"
            echo "  Downloads fmriprep launcher scripts to DIR (default: ~/bin)"
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

BASE_URL="https://raw.githubusercontent.com/${REPO}/${BRANCH}/fmriprep"

mkdir -p "$PREFIX"
echo "Installing fmriprep launcher to ${PREFIX} ..."

for f in "${SCRIPTS[@]}"; do
    echo "  ${f}"
    curl -fsSL "${BASE_URL}/${f}" -o "${PREFIX}/${f}"
    chmod +x "${PREFIX}/${f}"
done

echo ""
echo "Installed ${#SCRIPTS[@]} files to ${PREFIX}"
echo ""
echo "Quick start:"
echo "  cd /path/to/my_bids_dataset"
echo "  fmriprep_launcher.py init"
echo "  fmriprep_launcher.py wizard --quick"

# Check if PREFIX is on PATH
case ":${PATH}:" in
    *":${PREFIX}:"*) ;;
    *)
        echo ""
        echo "NOTE: ${PREFIX} is not on your PATH. Add it with:"
        echo "  echo 'export PATH=\"${PREFIX}:\$PATH\"' >> ~/.bashrc"
        ;;
esac
