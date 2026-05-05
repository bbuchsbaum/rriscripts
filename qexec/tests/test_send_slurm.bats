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

@test "pack dry-run: distributes stdin across packed batches" {
    run bash -lc "printf 'echo 1\necho 2\necho 3\necho 4\necho 5\necho 6\necho 7\n' | '$SEND_SLURM' --dry-run --state-dir '$TMPDIR' --nodes 5 --pack 3 -j packtest"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Persisted commands file:"* ]]
    [[ "$output" != *"Persisted runner script:"* ]]
    [[ "$output" == *"Submitting 7 command(s) across 5 packed batch(es), up to 3 concurrent command(s) per batch"* ]]
    [[ "$output" == *"--array=1-5"* ]]
    [[ "$output" == *"NCPUS=3"* ]]
    [[ "$output" == *"NODES=1"* ]]
    [[ "$output" == *"command_distributor.sh"* ]]
    [[ "$output" == *" 5 3"* ]]
}

@test "pack dry-run: explicit ncpus is preserved" {
    run bash -lc "printf 'echo one\necho two\n' | '$SEND_SLURM' --dry-run --state-dir '$TMPDIR' --nodes 2 --pack 3 --ncpus 8"
    [ "$status" -eq 0 ]
    [[ "$output" == *"NCPUS=8"* ]]
    [[ "$output" == *"NODES=1"* ]]
    [[ "$output" == *"command_distributor.sh"* ]]
}

@test "pack with explicit array fails" {
    run bash -lc "printf 'echo one\n' | '$SEND_SLURM' --dry-run --state-dir '$TMPDIR' --nodes 2 --pack 3 --array 1-2"
    [ "$status" -ne 0 ]
    [[ "$output" == *"--array cannot be used with --pack"* ]]
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
