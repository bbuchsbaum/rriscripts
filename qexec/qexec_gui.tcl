#!/usr/bin/env wish
# qexec_gui.tcl - A Tcl/Tk GUI front-end for qexec.sh

package require Tk

# --- Variables linked to GUI elements ---
set qexec_command ""
set qexec_time "1"
set qexec_ncpus "1"
set qexec_nodes "1"
set qexec_mem ""
set qexec_job_name ""
set qexec_array ""
set qexec_account "rrg-brad"
set qexec_omp_threads "1"
set qexec_interactive 0
set qexec_nox11 0
set qexec_log_dir ""
set qexec_dry_run 0

# --- Helpers ---
proc find_script {name} {
    set here [file dirname [file normalize [info script]]]
    set candidate [file join $here $name]
    if {[file executable $candidate]} {
        return $candidate
    }
    set candidate [auto_execok $name]
    if {$candidate eq ""} {
        return ""
    }
    return $candidate
}

proc error_box {msg} {
    tk_messageBox -icon error -type ok -title "Error" -message $msg
}

# Simple tokenizer that respects double and single quotes
proc tokenize_command {str} {
    set tokens {}
    set current ""
    set in_single 0
    set in_double 0
    foreach ch [split $str ""] {
        if {$in_single} {
            if {$ch eq "'"} {
                set in_single 0
            } else {
                append current $ch
            }
        } elseif {$in_double} {
            if {$ch eq "\""} {
                set in_double 0
            } else {
                append current $ch
            }
        } elseif {$ch eq "'"} {
            set in_single 1
        } elseif {$ch eq "\""} {
            set in_double 1
        } elseif {$ch eq " " || $ch eq "\t"} {
            if {$current ne ""} {
                lappend tokens $current
                set current ""
            }
        } else {
            append current $ch
        }
    }
    if {$current ne ""} {
        lappend tokens $current
    }
    return $tokens
}

# --- Tooltip support ---
namespace eval tooltip {
    variable afterid ""
    variable tip ""

    proc show {w msg} {
        variable afterid
        variable tip
        cancel
        set afterid [after 600 [list ::tooltip::display $w $msg]]
    }

    proc display {w msg} {
        variable tip
        catch {destroy .tooltip}
        set tip [toplevel .tooltip -bd 1 -relief solid -bg "#FFFFDD"]
        wm overrideredirect $tip 1
        wm attributes $tip -topmost 1
        label $tip.lbl -text $msg -bg "#FFFFDD" -fg black -padx 6 -pady 4 \
            -wraplength 300 -justify left -font {TkDefaultFont 9}
        pack $tip.lbl
        set x [expr {[winfo pointerx $w] + 12}]
        set y [expr {[winfo pointery $w] + 16}]
        wm geometry $tip +$x+$y
    }

    proc cancel {} {
        variable afterid
        variable tip
        if {$afterid ne ""} {
            after cancel $afterid
            set afterid ""
        }
        catch {destroy .tooltip}
    }
}

proc set_tooltip {w msg} {
    bind $w <Enter> [list ::tooltip::show %W $msg]
    bind $w <Leave> {::tooltip::cancel}
    bind $w <ButtonPress> {::tooltip::cancel}
}

proc append_output {msg} {
    .output.text configure -state normal
    .output.text insert end "$msg\n"
    .output.text see end
    .output.text configure -state disabled
}

proc clear_output {} {
    .output.text configure -state normal
    .output.text delete 1.0 end
    .output.text configure -state disabled
}

# --- GUI Layout ---
wm title . "qexec.sh GUI"
wm minsize . 600 480

# Frame for options
frame .options -borderwidth 2 -relief groove
pack .options -padx 8 -pady 8 -fill x

grid columnconfigure .options 1 -weight 1
grid columnconfigure .options 3 -weight 1

# Command Entry (Row 0)
label .options.lbl_cmd -text "Command:"
entry .options.ent_cmd -textvariable qexec_command -width 60
grid .options.lbl_cmd -row 0 -column 0 -sticky w -padx 4 -pady 2
grid .options.ent_cmd -row 0 -column 1 -columnspan 3 -sticky ew -padx 4 -pady 2
set_tooltip .options.ent_cmd "The shell command to run on the compute node.\nExample: Rscript myscript.R --arg value"

# Time & CPUs (Row 1)
label .options.lbl_time -text "Time (hours):"
entry .options.ent_time -textvariable qexec_time -width 8
label .options.lbl_ncpus -text "CPUs:"
entry .options.ent_ncpus -textvariable qexec_ncpus -width 8
grid .options.lbl_time   -row 1 -column 0 -sticky w -padx 4 -pady 2
grid .options.ent_time   -row 1 -column 1 -sticky w -padx 4 -pady 2
grid .options.lbl_ncpus  -row 1 -column 2 -sticky w -padx 4 -pady 2
grid .options.ent_ncpus  -row 1 -column 3 -sticky w -padx 4 -pady 2
set_tooltip .options.ent_time "Wall-clock time limit in whole hours.\nJob is killed if it exceeds this."
set_tooltip .options.ent_ncpus "Number of CPU cores per task.\nMatch this to your code's parallelism (e.g., R future::plan workers)."

# Memory & Nodes (Row 2)
label .options.lbl_mem -text "Memory (e.g., 6G):"
entry .options.ent_mem -textvariable qexec_mem -width 10
label .options.lbl_nodes -text "Nodes:"
entry .options.ent_nodes -textvariable qexec_nodes -width 8
grid .options.lbl_mem    -row 2 -column 0 -sticky w -padx 4 -pady 2
grid .options.ent_mem    -row 2 -column 1 -sticky w -padx 4 -pady 2
grid .options.lbl_nodes  -row 2 -column 2 -sticky w -padx 4 -pady 2
grid .options.ent_nodes  -row 2 -column 3 -sticky w -padx 4 -pady 2
set_tooltip .options.ent_mem "RAM per node. Use K, M, or G suffix.\nLeave blank to use cluster defaults."
set_tooltip .options.ent_nodes "Number of compute nodes to request.\nUsually 1 unless you need distributed computing."

# Job Name & Array (Row 3)
label .options.lbl_name -text "Job Name:"
entry .options.ent_name -textvariable qexec_job_name -width 20
label .options.lbl_array -text "Array (e.g., 1-10):"
entry .options.ent_array -textvariable qexec_array -width 15
grid .options.lbl_name   -row 3 -column 0 -sticky w -padx 4 -pady 2
grid .options.ent_name   -row 3 -column 1 -sticky ew -padx 4 -pady 2
grid .options.lbl_array  -row 3 -column 2 -sticky w -padx 4 -pady 2
grid .options.ent_array  -row 3 -column 3 -sticky ew -padx 4 -pady 2
set_tooltip .options.ent_name "A short label for your job in the SLURM queue.\nShows up in squeue output."
set_tooltip .options.ent_array "Submit multiple tasks as an array job.\nFormat: START-END or START-END%MAX_CONCURRENT\nExample: 1-100%10 runs 100 tasks, 10 at a time."

# Account & OMP Threads (Row 4)
label .options.lbl_account -text "Account:"
entry .options.ent_account -textvariable qexec_account -width 20
label .options.lbl_omp -text "OMP Threads:"
entry .options.ent_omp -textvariable qexec_omp_threads -width 8
grid .options.lbl_account -row 4 -column 0 -sticky w -padx 4 -pady 2
grid .options.ent_account -row 4 -column 1 -sticky ew -padx 4 -pady 2
grid .options.lbl_omp     -row 4 -column 2 -sticky w -padx 4 -pady 2
grid .options.ent_omp     -row 4 -column 3 -sticky w -padx 4 -pady 2
set_tooltip .options.ent_account "SLURM account for billing/priority.\nAsk your PI or check 'sacctmgr show assoc user=\$USER'."
set_tooltip .options.ent_omp "Sets OMP_NUM_THREADS and MKL_NUM_THREADS.\nControls parallelism in OpenMP/MKL code (R's BLAS, etc.)."

# Checkboxes (Row 5)
checkbutton .options.chk_interactive -text "Interactive Job" -variable qexec_interactive -command toggleCommandEntry
checkbutton .options.chk_nox11 -text "Disable X11" -variable qexec_nox11
grid .options.chk_interactive -row 5 -column 0 -columnspan 2 -sticky w -padx 4 -pady 2
grid .options.chk_nox11       -row 5 -column 2 -columnspan 2 -sticky w -padx 4 -pady 2
set_tooltip .options.chk_interactive "Get a shell on a compute node (salloc).\nCommand field is ignored in interactive mode."
set_tooltip .options.chk_nox11 "Disable X11 forwarding.\nUncheck if you need graphical apps (e.g., R plots)."

# Log Dir and Dry-Run (Row 6)
label .options.lbl_logdir -text "Log Dir:"
entry .options.ent_logdir -textvariable qexec_log_dir -width 30
checkbutton .options.chk_dryrun -text "Dry Run" -variable qexec_dry_run
grid .options.lbl_logdir  -row 6 -column 0 -sticky w -padx 4 -pady 2
grid .options.ent_logdir  -row 6 -column 1 -sticky ew -padx 4 -pady 2
grid .options.chk_dryrun  -row 6 -column 2 -columnspan 2 -sticky w -padx 4 -pady 2
set_tooltip .options.ent_logdir "Directory for SLURM .out/.err log files.\nLeave blank for current directory."
set_tooltip .options.chk_dryrun "Show the SLURM command without submitting.\nUse this to verify your settings first!"

# Buttons
frame .buttons
pack .buttons -padx 8 -pady 4 -fill x

button .buttons.submit -text "Submit Job" -command submitJob
button .buttons.clear -text "Clear Output" -command clear_output
button .buttons.quit -text "Quit" -command exit
pack .buttons.quit -side right -padx 4
pack .buttons.clear -side right -padx 4
pack .buttons.submit -side right -padx 4

# Output pane
frame .output -borderwidth 2 -relief groove
pack .output -padx 8 -pady 4 -fill both -expand 1

label .output.lbl -text "Output:" -anchor w
pack .output.lbl -side top -fill x -padx 4 -pady 2

text .output.text -height 10 -wrap word -state disabled -font {TkFixedFont 10} \
    -bg "#F8F8F8" -relief sunken -borderwidth 1
scrollbar .output.scroll -command {.output.text yview}
.output.text configure -yscrollcommand {.output.scroll set}
pack .output.scroll -side right -fill y
pack .output.text -side left -fill both -expand 1 -padx 4 -pady 2

# Status bar
label .statusbar -text "Ready. Check 'Dry Run' to preview without submitting." \
    -anchor w -relief sunken -borderwidth 1 -padx 4
pack .statusbar -side bottom -fill x -padx 8 -pady 4

# --- Procedures ---

proc toggleCommandEntry {} {
    global qexec_interactive
    if {$qexec_interactive} {
        .options.ent_cmd configure -state disabled
        .options.ent_array configure -state disabled
    } else {
        .options.ent_cmd configure -state normal
        .options.ent_array configure -state normal
    }
}

proc submitJob {} {
    global qexec_command qexec_time qexec_ncpus qexec_nodes qexec_mem \
           qexec_job_name qexec_array qexec_account qexec_omp_threads \
           qexec_interactive qexec_nox11 qexec_log_dir qexec_dry_run

    set qexec_script [find_script qexec.sh]
    if {$qexec_script eq ""} {
        error_box "qexec.sh not found next to GUI or in PATH."
        return
    }

    set cmd_list [list $qexec_script]

    # Interactive flag
    if {$qexec_interactive} {
        lappend cmd_list "-i"
    }

    # Time
    if {[string trim $qexec_time] eq ""} {
        error_box "Time cannot be empty."
        return
    }
    if {![string is integer -strict $qexec_time] || $qexec_time <= 0} {
        error_box "Time must be a positive integer (hours)."
        return
    }
    lappend cmd_list "-t" $qexec_time

    # CPUs
    if {[string trim $qexec_ncpus] ne ""} {
        if {![string is integer -strict $qexec_ncpus] || $qexec_ncpus <= 0} {
            error_box "CPUs must be a positive integer."
            return
        }
        lappend cmd_list "-n" $qexec_ncpus
    }

    # Nodes
    if {[string trim $qexec_nodes] ne ""} {
        if {![string is integer -strict $qexec_nodes] || $qexec_nodes <= 0} {
            error_box "Nodes must be a positive integer."
            return
        }
        lappend cmd_list "--nodes" $qexec_nodes
    }

    # Memory
    if {[string trim $qexec_mem] ne ""} {
        if {![regexp {^[0-9]+[KMGkmg]$} $qexec_mem]} {
            error_box "Memory must be like '6G', '512M', '1024K', etc."
            return
        }
        lappend cmd_list "-m" [string toupper $qexec_mem]
    }

    # Job Name
    if {[string trim $qexec_job_name] ne ""} {
        lappend cmd_list "-j" $qexec_job_name
    }

    # Array
    if {[string trim $qexec_array] ne ""} {
        if {![regexp {^[0-9]+(-[0-9]+)?(%[0-9]+)?$} $qexec_array]} {
            error_box "Invalid Array format. Use e.g., 1-5 or 1-10%2."
            return
        }
        lappend cmd_list "-a" $qexec_array
    }

    # Account
    if {[string trim $qexec_account] eq ""} {
        error_box "Account cannot be empty."
        return
    }
    lappend cmd_list "--account" $qexec_account

    # OMP Threads
    if {[string trim $qexec_omp_threads] ne ""} {
        if {![string is integer -strict $qexec_omp_threads] || $qexec_omp_threads <= 0} {
            error_box "OMP Threads must be a positive integer."
            return
        }
        lappend cmd_list "-o" $qexec_omp_threads
    }

    # NoX11
    if {$qexec_nox11} {
        lappend cmd_list "--nox11"
    }

    # Log Dir
    if {[string trim $qexec_log_dir] ne ""} {
        lappend cmd_list "-l" $qexec_log_dir
    }

    # Dry Run
    if {$qexec_dry_run} {
        lappend cmd_list "-d"
    }

    # Command (tokenized properly to preserve quoted arguments)
    if {!$qexec_interactive} {
        if {[string trim $qexec_command] eq ""} {
            error_box "Command cannot be empty for batch jobs."
            return
        }
        lappend cmd_list "--"
        foreach tok [tokenize_command $qexec_command] {
            lappend cmd_list $tok
        }
    }

    # Confirm unless dry-run
    if {!$qexec_dry_run} {
        set answer [tk_messageBox -icon question -type yesno \
            -title "Confirm Submission" \
            -message "Submit the following job?\n\n[join $cmd_list " "]"]
        if {$answer eq "no"} {
            return
        }
    }

    clear_output
    append_output "Running: [join $cmd_list " "]"
    append_output "---"
    .statusbar configure -text "Submitting..."
    update idletasks

    # Execute synchronously and capture all output
    set code [catch {exec {*}$cmd_list 2>@1} result]
    if {$result ne ""} {
        append_output $result
    }
    if {$code != 0} {
        append_output "\n--- ERROR ---"
        .statusbar configure -text "Error during submission."
    } else {
        if {$qexec_dry_run} {
            .statusbar configure -text "Dry run complete. Review output above."
        } else {
            .statusbar configure -text "Job submitted successfully."
        }
    }
}

# Initialize
toggleCommandEntry

# Center the window
update idletasks
set sw [winfo screenwidth .]
set sh [winfo screenheight .]
set w [winfo reqwidth .]
set h [winfo reqheight .]
set x [expr {($sw - $w) / 2}]
set y [expr {($sh - $h) / 3}]
wm geometry . +$x+$y
