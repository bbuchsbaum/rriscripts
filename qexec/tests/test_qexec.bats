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

@test "batch dry-run: fractional hours are accepted" {
    run "$QEXEC" --dry-run -t .5 -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"TIME=.5"* ]]
    [[ "$output" == *"minutes=30"* ]]
}

@test "batch dry-run: minute suffix is accepted" {
    run "$QEXEC" --dry-run -t 30m -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"TIME=30m"* ]]
    [[ "$output" == *"minutes=30"* ]]
}

@test "batch dry-run: hour suffix is accepted" {
    run "$QEXEC" --dry-run -t 1hr -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"TIME=1hr"* ]]
    [[ "$output" == *"minutes=60"* ]]
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

@test "batch dry-run: supports equals-style long options" {
    run "$QEXEC" --dry-run --time=3 --ncpus=2 --account=myaccount --array=1-3 -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"TIME=3"* ]]
    [[ "$output" == *"NCPUS=2"* ]]
    [[ "$output" == *"ACCOUNT=myaccount"* ]]
    [[ "$output" == *"ARRAY=1-3"* ]]
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
    [[ "$output" != *"Enhanced getopt not found"* ]]
}

@test "batch dry-run: omp threads" {
    run "$QEXEC" --dry-run -o 4 -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"OMP_NUM_THREADS=4"* ]]
}

@test "batch dry-run: preserves user command arguments" {
    run "$QEXEC" --dry-run -- myscript.sh --array=foo
    [ "$status" -eq 0 ]
    [[ "$output" == *"myscript.sh --array=foo"* ]]
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
    [[ "$output" == *"positive duration"* ]]
}

@test "time=0 fails" {
    run "$QEXEC" --dry-run -t 0 -- myscript.sh
    [ "$status" -ne 0 ]
    [[ "$output" == *"positive duration"* ]]
}

@test "invalid ncpus value fails" {
    run "$QEXEC" --dry-run -n 0 -- myscript.sh
    [ "$status" -ne 0 ]
    [[ "$output" == *"--ncpus"* ]]
}

@test "invalid omp thread value fails" {
    run "$QEXEC" --dry-run -o 0 -- myscript.sh
    [ "$status" -ne 0 ]
    [[ "$output" == *"--omp_num_threads"* ]]
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

# ── --cmd-file ────────────────────────────────────────────────────

@test "cmd-file dry-run: sets array and command from file" {
    tmpfile=$(mktemp)
    printf 'echo hello\necho world\necho foo\n' > "$tmpfile"
    run "$QEXEC" --dry-run --cmd-file "$tmpfile"
    rm -f "$tmpfile"
    [ "$status" -eq 0 ]
    [[ "$output" == *"ARRAY=1-3"* ]]
    [[ "$output" == *"--array=1-3"* ]]
    [[ "$output" == *"SLURM_ARRAY_TASK_ID"* ]]
}

@test "cmd-file: nonexistent file fails" {
    run "$QEXEC" --dry-run --cmd-file /nonexistent
    [ "$status" -ne 0 ]
    [[ "$output" == *"does not exist"* ]]
}

@test "cmd-file: empty file fails" {
    tmpfile=$(mktemp)
    run "$QEXEC" --dry-run --cmd-file "$tmpfile"
    rm -f "$tmpfile"
    [ "$status" -ne 0 ]
    [[ "$output" == *"empty"* ]]
}

@test "cmd-file: conflicts with --array" {
    tmpfile=$(mktemp)
    echo "echo hi" > "$tmpfile"
    run "$QEXEC" --dry-run --cmd-file "$tmpfile" -a 1-5
    rm -f "$tmpfile"
    [ "$status" -ne 0 ]
    [[ "$output" == *"mutually exclusive"* ]]
}

@test "cmd-file: conflicts with positional command" {
    tmpfile=$(mktemp)
    echo "echo hi" > "$tmpfile"
    run "$QEXEC" --dry-run --cmd-file "$tmpfile" -- echo hello
    rm -f "$tmpfile"
    [ "$status" -ne 0 ]
    [[ "$output" == *"mutually exclusive"* ]]
}

# ── --preset ──────────────────────────────────────────────────────

@test "preset dry-run: fmriprep sets time, ncpus, mem" {
    run "$QEXEC" --dry-run --preset fmriprep -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"TIME=12"* ]]
    [[ "$output" == *"NCPUS=8"* ]]
    [[ "$output" == *"--mem=32G"* ]]
}

@test "preset dry-run: freesurfer sets time, ncpus, mem" {
    run "$QEXEC" --dry-run --preset freesurfer -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"TIME=24"* ]]
    [[ "$output" == *"NCPUS=1"* ]]
    [[ "$output" == *"--mem=8G"* ]]
}

@test "preset dry-run: CLI flags override preset" {
    run "$QEXEC" --dry-run --preset fmriprep -t 2 -n 4 -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"TIME=2"* ]]
    [[ "$output" == *"NCPUS=4"* ]]
    # mem should still come from preset
    [[ "$output" == *"--mem=32G"* ]]
}

@test "preset: unknown preset fails" {
    run "$QEXEC" --dry-run --preset bogus -- myscript.sh
    [ "$status" -ne 0 ]
    [[ "$output" == *"Unknown preset"* ]]
}

@test "preset dry-run: equals-style" {
    run "$QEXEC" --dry-run --preset=mriqc -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"TIME=4"* ]]
    [[ "$output" == *"NCPUS=4"* ]]
}

# ── --after ───────────────────────────────────────────────────────

@test "after dry-run: adds dependency flag" {
    run "$QEXEC" --dry-run --after 12345 -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"--dependency=afterok:12345"* ]]
}

@test "after dry-run: equals-style" {
    run "$QEXEC" --dry-run --after=67890 -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"--dependency=afterok:67890"* ]]
}

@test "after: non-numeric job ID fails" {
    run "$QEXEC" --dry-run --after abc -- myscript.sh
    [ "$status" -ne 0 ]
    [[ "$output" == *"numeric"* ]]
}

@test "after: incompatible with interactive mode" {
    run "$QEXEC" --dry-run -i --after 12345
    [ "$status" -ne 0 ]
    [[ "$output" == *"not supported with interactive"* ]]
}

# ── --wait ────────────────────────────────────────────────────────

@test "wait: incompatible with interactive mode" {
    run "$QEXEC" --dry-run -i --wait
    [ "$status" -ne 0 ]
    [[ "$output" == *"not supported with interactive"* ]]
}

# ── cluster detection ─────────────────────────────────────────────

@test "CC_CLUSTER=niagara sets no-mem and ncpus=40" {
    CC_CLUSTER=niagara run "$QEXEC" --dry-run -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"NCPUS=40"* ]]
    [[ "$output" == *"MEM_FLAG=<none>"* ]]
}

@test "CC_CLUSTER=niagara: CLI ncpus overrides cluster default" {
    CC_CLUSTER=niagara run "$QEXEC" --dry-run -n 8 -- myscript.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"NCPUS=8"* ]]
}

# ── qexecrc ───────────────────────────────────────────────────────

@test "QEXEC_CONFIG loads custom defaults" {
    tmprc=$(mktemp)
    echo 'ACCOUNT="def-mypi"' > "$tmprc"
    QEXEC_CONFIG="$tmprc" run "$QEXEC" --dry-run -- myscript.sh
    rm -f "$tmprc"
    [ "$status" -eq 0 ]
    [[ "$output" == *"ACCOUNT=def-mypi"* ]]
}

@test "QEXEC_CONFIG: CLI overrides config file" {
    tmprc=$(mktemp)
    echo 'TIME=8' > "$tmprc"
    QEXEC_CONFIG="$tmprc" run "$QEXEC" --dry-run -t 2 -- myscript.sh
    rm -f "$tmprc"
    [ "$status" -eq 0 ]
    [[ "$output" == *"TIME=2"* ]]
}

@test "missing qexecrc is silently ignored" {
    QEXEC_CONFIG=/nonexistent/qexecrc run "$QEXEC" --dry-run -- myscript.sh
    [ "$status" -eq 0 ]
}
