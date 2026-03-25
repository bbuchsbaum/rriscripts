#!/bin/bash
set -euo pipefail

# Install fmriprep launcher to ~/.local/share/fmriprep with a symlink in ~/bin.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/fmriprep/install.sh | bash
#   curl -fsSL ... | bash -s -- --lib-dir ~/.fmriprep --bin-dir ~/bin

REPO="bbuchsbaum/rriscripts"
BRANCH="main"
LIB_DIR="${HOME}/.local/share/fmriprep"
BIN_DIR="${HOME}/bin"

SCRIPTS=(
    fmriprep_launcher.py
    fmriprep_backend.py
    fmriprep_shared.py
    fmriprep_tui_autocomplete.py
    fmriprep_gui_tk.py
    fmriprep_command_builder.py
    run_fmriprep_wizard.sh
    slurm_batched_template.sh
    fmriprep_config_example.ini
    fmriprep_project_example.ini
)

# Entry points to symlink into BIN_DIR
ENTRY_POINTS=(
    fmriprep_launcher.py
    run_fmriprep_wizard.sh
)

while [[ $# -gt 0 ]]; do
    case "$1" in
        --lib-dir) LIB_DIR="$2"; shift 2 ;;
        --lib-dir=*) LIB_DIR="${1#--lib-dir=}"; shift ;;
        --bin-dir) BIN_DIR="$2"; shift 2 ;;
        --bin-dir=*) BIN_DIR="${1#--bin-dir=}"; shift ;;
        -h|--help)
            echo "Usage: install.sh [--lib-dir DIR] [--bin-dir DIR]"
            echo "  --lib-dir  Where to install all files (default: ~/.local/share/fmriprep)"
            echo "  --bin-dir  Where to place symlinks for entry points (default: ~/bin)"
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

BASE_URL="https://raw.githubusercontent.com/${REPO}/${BRANCH}/fmriprep"

mkdir -p "$LIB_DIR" "$BIN_DIR"
echo "Installing fmriprep launcher to ${LIB_DIR} ..."

for f in "${SCRIPTS[@]}"; do
    echo "  ${f}"
    curl -fsSL "${BASE_URL}/${f}" -o "${LIB_DIR}/${f}"
    chmod +x "${LIB_DIR}/${f}"
done

echo ""
echo "Creating symlinks in ${BIN_DIR} ..."
for ep in "${ENTRY_POINTS[@]}"; do
    ln -sf "${LIB_DIR}/${ep}" "${BIN_DIR}/${ep}"
    echo "  ${BIN_DIR}/${ep} -> ${LIB_DIR}/${ep}"
done

echo ""
echo "Installed ${#SCRIPTS[@]} files to ${LIB_DIR}"
echo "Symlinked ${#ENTRY_POINTS[@]} entry points to ${BIN_DIR}"
echo ""
echo "Quick start:"
echo "  cd /path/to/my_bids_dataset"
echo "  fmriprep_launcher.py init"
echo "  fmriprep_launcher.py wizard --quick"

# Check if BIN_DIR is on PATH
case ":${PATH}:" in
    *":${BIN_DIR}:"*) ;;
    *)
        echo ""
        echo "NOTE: ${BIN_DIR} is not on your PATH. Add it with:"
        echo "  echo 'export PATH=\"${BIN_DIR}:\$PATH\"' >> ~/.bashrc"
        ;;
esac
