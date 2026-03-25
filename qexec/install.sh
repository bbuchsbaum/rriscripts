#!/bin/bash
set -euo pipefail

# Install qexec scripts to ~/bin (or a custom directory).
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/qexec/install.sh | bash
#   curl -fsSL ... | bash -s -- --prefix /opt/bin

REPO="bbuchsbaum/rriscripts"
BRANCH="main"
PREFIX="${HOME}/bin"

SCRIPTS=(
    qexec.sh
    cmd_expand.sh
    batch_exec.sh
    bexec.sh
    command_distributor.sh
    send_slurm.sh
    slurm_job_monitor.sh
    rjobtop.py
)

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix) PREFIX="$2"; shift 2 ;;
        --prefix=*) PREFIX="${1#--prefix=}"; shift ;;
        -h|--help)
            echo "Usage: install.sh [--prefix DIR]"
            echo "  Downloads qexec scripts to DIR (default: ~/bin)"
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

BASE_URL="https://raw.githubusercontent.com/${REPO}/${BRANCH}/qexec"

mkdir -p "$PREFIX"
echo "Installing qexec to ${PREFIX} ..."

for f in "${SCRIPTS[@]}"; do
    echo "  ${f}"
    curl -fsSL "${BASE_URL}/${f}" -o "${PREFIX}/${f}"
    chmod +x "${PREFIX}/${f}"
done

echo ""
echo "Installed ${#SCRIPTS[@]} scripts to ${PREFIX}"

# Check if PREFIX is on PATH
case ":${PATH}:" in
    *":${PREFIX}:"*) ;;
    *)
        echo ""
        echo "NOTE: ${PREFIX} is not on your PATH. Add it with:"
        echo "  echo 'export PATH=\"${PREFIX}:\$PATH\"' >> ~/.bashrc"
        ;;
esac
