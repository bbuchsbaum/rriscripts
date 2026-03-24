#!/usr/bin/env bats
# Tests for send_slurm.sh (using qexec --dry-run)

setup() {
    SEND_SLURM="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)/send_slurm.sh"
    TMPDIR="$(mktemp -d)"
}

teardown() {
    rm -rf "$TMPDIR"
}

@test "dry-run: persists command and runner files" {
    run bash -lc "printf 'echo one\necho two\n' | '$SEND_SLURM' --dry-run --state-dir '$TMPDIR' -j sendtest"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Persisted commands file:"* ]]
    [[ "$output" == *"Persisted runner script:"* ]]
    [[ "$output" == *"--array=1-2"* ]]
    [[ "$output" == *"Dry-run"* ]]
}

@test "empty stdin fails" {
    run bash -lc "printf '' | '$SEND_SLURM' --dry-run --state-dir '$TMPDIR'"
    [ "$status" -ne 0 ]
    [[ "$output" == *"No commands provided"* ]]
}

@test "invalid mem fails" {
    run bash -lc "printf 'echo one\n' | '$SEND_SLURM' --dry-run --state-dir '$TMPDIR' --mem bad"
    [ "$status" -ne 0 ]
    [[ "$output" == *"--mem"* ]]
}
