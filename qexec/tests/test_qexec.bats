#!/usr/bin/env bats
# Tests for qexec.sh (using --dry-run to avoid needing SLURM)

setup() {
    QEXEC="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)/qexec.sh"
    # Unset env vars that could interfere
    unset QEXEC_DISABLE_MEM
    unset QEXEC_DEFAULT_MEM
    unset QEXEC_LOG_DIR
}

# ── Batch dry-run ──────────────────────────────────────────────────

@test "batch dry-run: basic command" {
    run "$QEXEC" --dry-run -- echo hello
    [ "$status" -eq 0 ]
    [[ "$output" == *"Dry-run"* ]]
    [[ "$output" == *"TIME=1"* ]]
    [[ "$output" == *"sbatch"* ]]
    [[ "$output" == *"echo hello"* ]]
}

@test "batch dry-run: custom time and ncpus" {
    run "$QEXEC" --dry-run -t 4 -n 8 -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"TIME=4"* ]]
    [[ "$output" == *"minutes=240"* ]]
    [[ "$output" == *"NCPUS=8"* ]]
}

@test "batch dry-run: memory flag" {
    run "$QEXEC" --dry-run -m 16G -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"--mem=16G"* ]]
}

@test "batch dry-run: array job" {
    run "$QEXEC" --dry-run -a 1-10 -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"ARRAY=1-10"* ]]
    [[ "$output" == *"--array=1-10"* ]]
}

@test "batch dry-run: array with throttle" {
    run "$QEXEC" --dry-run -a 1-20%5 -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"ARRAY=1-20%5"* ]]
}

@test "batch dry-run: job name" {
    run "$QEXEC" --dry-run -j myjob -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"--job-name=myjob"* ]]
}

@test "batch dry-run: custom account" {
    run "$QEXEC" --dry-run --account myaccount -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"ACCOUNT=myaccount"* ]]
}

@test "batch dry-run: log directory" {
    run "$QEXEC" --dry-run -l /tmp/logs -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"/tmp/logs/slurm-%j.out"* ]]
}

@test "batch dry-run: no eval in job script" {
    run "$QEXEC" --dry-run -- echo hello world
    [ "$status" -eq 0 ]
    # The job script content should NOT contain eval
    [[ "$output" != *"eval"* ]]
}

@test "batch dry-run: omp threads" {
    run "$QEXEC" --dry-run -o 4 -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"OMP_NUM_THREADS=4"* ]]
}

# ── Interactive dry-run ────────────────────────────────────────────

@test "interactive dry-run: basic" {
    run "$QEXEC" --dry-run -i
    [ "$status" -eq 0 ]
    [[ "$output" == *"Dry-run"* ]]
    [[ "$output" == *"salloc"* ]]
    [[ "$output" == *"--x11"* ]]
}

@test "interactive dry-run: nox11" {
    run "$QEXEC" --dry-run -i --nox11
    [ "$status" -eq 0 ]
    [[ "$output" == *"salloc"* ]]
    [[ "$output" != *"--x11"* ]]
}

@test "interactive dry-run: custom resources" {
    run "$QEXEC" --dry-run -i -t 2 -n 4 -m 8G
    [ "$status" -eq 0 ]
    [[ "$output" == *"minutes=120"* ]]
    [[ "$output" == *"--mem=8G"* ]]
}

# ── Validation ─────────────────────────────────────────────────────

@test "missing command in batch mode fails" {
    run "$QEXEC" --dry-run
    [ "$status" -ne 0 ]
    [[ "$output" == *"command is required"* ]] || [[ "$output" == *"Error"* ]]
}

@test "invalid time value fails" {
    run "$QEXEC" --dry-run -t abc -- myscript.sh
    [ "$status" -ne 0 ]
    [[ "$output" == *"positive integer"* ]]
}

@test "time=0 fails" {
    run "$QEXEC" --dry-run -t 0 -- myscript.sh
    [ "$status" -ne 0 ]
    [[ "$output" == *"positive integer"* ]]
}

@test "invalid array range fails" {
    run "$QEXEC" --dry-run -a "bad" -- myscript.sh
    [ "$status" -ne 0 ]
    [[ "$output" == *"valid range"* ]]
}

# ── Environment variables ─────────────────────────────────────────

@test "QEXEC_DISABLE_MEM suppresses --mem" {
    QEXEC_DISABLE_MEM=1 run "$QEXEC" --dry-run -m 16G -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"MEM_FLAG=<none>"* ]] || [[ "$output" != *"--mem=16G"* ]]
}

@test "QEXEC_DEFAULT_MEM provides default" {
    QEXEC_DEFAULT_MEM=4G run "$QEXEC" --dry-run -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"--mem=4G"* ]]
}

@test "--no-mem suppresses --mem" {
    run "$QEXEC" --dry-run --no-mem -m 16G -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"MEM_FLAG=<none>"* ]] || [[ "$output" != *"--mem="* ]]
}

# ── Help ───────────────────────────────────────────────────────────

@test "help flag shows usage" {
    run "$QEXEC" --help
    # usage exits with 1
    [[ "$output" == *"Usage"* ]]
}
