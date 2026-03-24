#!/usr/bin/env wish
# batch_exec_gui.tcl - A Tcl/Tk front-end for batch_exec.sh

package require Tk

# --- State variables ---
set bex_cmd ""
set bex_time "1"
set bex_nodes "1"
set bex_ncpus "40"
set bex_mem ""
set bex_jobs "40"
set bex_name ""
set bex_account "rrg-brad"
set bex_logdir ""
set bex_link 0
set bex_quote 0
set bex_dryrun 0
set bex_helper_opt ""
set bex_helper_vals ""

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

proc info_box {title msg} {
    tk_messageBox -icon info -type ok -title $title -message $msg
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
wm title . "batch_exec GUI"
wm minsize . 650 550

frame .options -borderwidth 2 -relief groove
pack .options -padx 8 -pady 8 -fill both -expand 0

grid columnconfigure .options 1 -weight 1
grid columnconfigure .options 3 -weight 1

# Command entry (Row 0-1)
label .options.lbl_cmd -text "Base command (use \[..\] for expansion):"
entry .options.ent_cmd -textvariable bex_cmd -width 70
grid .options.lbl_cmd -row 0 -column 0 -columnspan 4 -sticky w -padx 4 -pady 2
grid .options.ent_cmd -row 1 -column 0 -columnspan 4 -sticky ew -padx 4 -pady 4
set_tooltip .options.ent_cmd "Enter your command with \[..\] brackets for parameter expansion.\nExamples:\n  Rscript run.R --sub \[1..100\] --method \[lasso,ridge\]\n  prog -f \[file:subjects.txt\] -o output"

# Time & Nodes (Row 2)
label .options.lbl_time -text "Time (hrs):"
entry .options.ent_time -textvariable bex_time -width 8
label .options.lbl_nodes -text "Nodes / array size:"
entry .options.ent_nodes -textvariable bex_nodes -width 8
grid .options.lbl_time  -row 2 -column 0 -sticky w -padx 4 -pady 2
grid .options.ent_time  -row 2 -column 1 -sticky w -padx 4 -pady 2
grid .options.lbl_nodes -row 2 -column 2 -sticky w -padx 4 -pady 2
grid .options.ent_nodes -row 2 -column 3 -sticky w -padx 4 -pady 2
set_tooltip .options.ent_time "Wall-clock time limit per array task, in hours.\nJob is killed if it exceeds this."
set_tooltip .options.ent_nodes "How many SLURM array tasks to create.\nCommands are split evenly across these nodes.\nMore nodes = faster but uses more allocation."

# CPUs & Jobs (Row 3)
label .options.lbl_ncpus -text "CPUs per task:"
entry .options.ent_ncpus -textvariable bex_ncpus -width 8
label .options.lbl_jobs -text "Parallel jobs per node:"
entry .options.ent_jobs -textvariable bex_jobs -width 8
grid .options.lbl_ncpus -row 3 -column 0 -sticky w -padx 4 -pady 2
grid .options.ent_ncpus -row 3 -column 1 -sticky w -padx 4 -pady 2
grid .options.lbl_jobs  -row 3 -column 2 -sticky w -padx 4 -pady 2
grid .options.ent_jobs  -row 3 -column 3 -sticky w -padx 4 -pady 2
set_tooltip .options.ent_ncpus "Number of CPU cores allocated per array task.\nTypically 40 for a full node on many clusters."
set_tooltip .options.ent_jobs "How many commands GNU Parallel runs concurrently on each node.\nUsually matches CPUs if each command uses 1 core."

# Memory & Job Name (Row 4)
label .options.lbl_mem -text "Memory (e.g., 6G):"
entry .options.ent_mem -textvariable bex_mem -width 10
label .options.lbl_name -text "Job name:"
entry .options.ent_name -textvariable bex_name -width 15
grid .options.lbl_mem  -row 4 -column 0 -sticky w -padx 4 -pady 2
grid .options.ent_mem  -row 4 -column 1 -sticky w -padx 4 -pady 2
grid .options.lbl_name -row 4 -column 2 -sticky w -padx 4 -pady 2
grid .options.ent_name -row 4 -column 3 -sticky w -padx 4 -pady 2
set_tooltip .options.ent_mem "RAM per node. Use K, M, or G suffix.\nLeave blank to use cluster defaults."
set_tooltip .options.ent_name "A short label for your job in the SLURM queue.\nShows up in squeue output."

# Account & Log Dir (Row 5)
label .options.lbl_account -text "Account:"
entry .options.ent_account -textvariable bex_account -width 15
label .options.lbl_logdir -text "Log dir:"
entry .options.ent_logdir -textvariable bex_logdir -width 25
grid .options.lbl_account -row 5 -column 0 -sticky w -padx 4 -pady 2
grid .options.ent_account -row 5 -column 1 -sticky w -padx 4 -pady 2
grid .options.lbl_logdir -row 5 -column 2 -sticky w -padx 4 -pady 2
grid .options.ent_logdir -row 5 -column 3 -sticky ew -padx 4 -pady 2
set_tooltip .options.ent_account "SLURM account for billing/priority.\nAsk your PI or check 'sacctmgr show assoc user=\$USER'."
set_tooltip .options.ent_logdir "Directory for SLURM .out/.err log files.\nLeave blank for current directory."

# Checkboxes (Row 6)
checkbutton .options.chk_link  -text "Link mode (zip args)" -variable bex_link
checkbutton .options.chk_quote -text "Quote tokens"        -variable bex_quote
checkbutton .options.chk_dry   -text "Dry run only"        -variable bex_dryrun
grid .options.chk_link  -row 6 -column 0 -columnspan 2 -sticky w -padx 4 -pady 2
grid .options.chk_quote -row 6 -column 2 -sticky w -padx 4 -pady 2
grid .options.chk_dry   -row 6 -column 3 -sticky w -padx 4 -pady 2
set_tooltip .options.chk_link "Default: Cartesian product (all combinations).\nLink mode: zip arguments by position instead.\nShorter lists repeat their last value."
set_tooltip .options.chk_quote "Shell-quote each token in the expanded commands.\nUseful when values contain spaces or special characters."
set_tooltip .options.chk_dry "Show expanded commands and the SLURM submission\ncommand without actually submitting.\nUse this to verify before real submission!"

# Example hint (Row 7)
label .options.help -text "Example: myprog -a \[1,2,3\] --flag \[x,y\] --opt \[file:/tmp/list.txt\]" \
    -anchor w -justify left -foreground "#555555"
grid .options.help -row 7 -column 0 -columnspan 4 -sticky w -padx 4 -pady 4

# --- Argument helper ---
frame .arghelper -borderwidth 2 -relief groove
pack .arghelper -padx 8 -pady 4 -fill x

label .arghelper.title -text "Argument Helper" -font {TkDefaultFont 10 bold} -anchor w
grid .arghelper.title -row 0 -column 0 -columnspan 3 -sticky w -padx 4 -pady 4

label .arghelper.lbl -text "Build bracket expressions step by step. Values are auto-wrapped in \[..\]." \
    -foreground "#555555"
grid .arghelper.lbl -row 1 -column 0 -columnspan 3 -sticky w -padx 4 -pady 2

label .arghelper.lopt -text "Option (e.g., -a):"
entry .arghelper.eopt -textvariable bex_helper_opt -width 15
grid .arghelper.lopt -row 2 -column 0 -sticky w -padx 4 -pady 2
grid .arghelper.eopt -row 2 -column 1 -sticky w -padx 4 -pady 2
set_tooltip .arghelper.eopt "The flag name, e.g., -f or --subject.\nLeave blank for positional arguments."

label .arghelper.lval -text "Values (comma/range/file:):"
entry .arghelper.eval -textvariable bex_helper_vals -width 40
grid .arghelper.lval -row 3 -column 0 -sticky w -padx 4 -pady 2
grid .arghelper.eval -row 3 -column 1 -sticky w -padx 4 -pady 2
set_tooltip .arghelper.eval "Expansion values. Examples:\n  1,2,3       Comma-separated list\n  1..100      Integer range\n  file:/path  Lines from a file\n  df:col:file CSV column\n  glob:*.nii  File glob pattern"

button .arghelper.add -text "Add to Command" -command addArg
grid .arghelper.add -row 3 -column 2 -sticky ew -padx 4 -pady 2

# --- Buttons ---
frame .buttons
pack .buttons -padx 8 -pady 4 -fill x

button .buttons.submit  -text "Submit"  -command submitBatch
button .buttons.preview -text "Preview Expansion" -command previewExpansion
button .buttons.clear   -text "Clear Output" -command clear_output
button .buttons.quit    -text "Quit"    -command exit
pack .buttons.quit -side right -padx 4
pack .buttons.clear -side right -padx 4
pack .buttons.preview -side right -padx 4
pack .buttons.submit -side right -padx 4

# --- Output pane ---
frame .output -borderwidth 2 -relief groove
pack .output -padx 8 -pady 4 -fill both -expand 1

label .output.lbl -text "Output:" -anchor w
pack .output.lbl -side top -fill x -padx 4 -pady 2

text .output.text -height 12 -wrap word -state disabled -font {TkFixedFont 10} \
    -bg "#F8F8F8" -relief sunken -borderwidth 1
scrollbar .output.scroll -command {.output.text yview}
.output.text configure -yscrollcommand {.output.scroll set}
pack .output.scroll -side right -fill y
pack .output.text -side left -fill both -expand 1 -padx 4 -pady 2

# Status bar
label .statusbar -text "Ready. Use 'Preview Expansion' to see commands before submitting." \
    -anchor w -relief sunken -borderwidth 1 -padx 4
pack .statusbar -side bottom -fill x -padx 8 -pady 4

# --- Logic ---

proc build_batch_cmd {} {
    global bex_cmd bex_time bex_nodes bex_ncpus bex_mem bex_jobs \
           bex_name bex_account bex_logdir bex_link bex_quote bex_dryrun

    if {[string trim $bex_cmd] eq ""} {
        error_box "Base command cannot be empty."
        return ""
    }
    if {![string is integer -strict $bex_time] || $bex_time <= 0} {
        error_box "Time must be a positive integer (hours)."
        return ""
    }
    foreach {val label} [list $bex_nodes "Nodes" $bex_ncpus "CPUs" $bex_jobs "Jobs"] {
        if {![string is integer -strict $val] || $val <= 0} {
            error_box "$label must be a positive integer."
            return ""
        }
    }
    if {[string trim $bex_mem] ne ""} {
        if {![regexp {^[0-9]+[KMGkmg]$} $bex_mem]} {
            error_box "Memory must look like 6G, 512M, etc."
            return ""
        }
    }

    set script_path [find_script batch_exec.sh]
    if {$script_path eq ""} {
        error_box "batch_exec.sh not found next to GUI or in PATH."
        return ""
    }

    set cmdlist [list $script_path \
        --time $bex_time --nodes $bex_nodes --ncpus $bex_ncpus --jobs $bex_jobs]
    if {[string trim $bex_mem] ne ""} { lappend cmdlist --mem [string toupper $bex_mem] }
    if {[string trim $bex_name] ne ""} { lappend cmdlist --name $bex_name }
    if {[string trim $bex_account] ne ""} { lappend cmdlist --account $bex_account }
    if {[string trim $bex_logdir] ne ""} { lappend cmdlist --log-dir $bex_logdir }
    if {$bex_link} { lappend cmdlist --link }
    if {$bex_quote} { lappend cmdlist --quote }

    return $cmdlist
}

proc previewExpansion {} {
    global bex_cmd bex_link bex_quote

    if {[string trim $bex_cmd] eq ""} {
        error_box "Base command cannot be empty."
        return
    }

    set expand_path [find_script cmd_expand.sh]
    if {$expand_path eq ""} {
        error_box "cmd_expand.sh not found next to GUI or in PATH."
        return
    }

    set cmdlist [list $expand_path]
    if {$bex_link} { lappend cmdlist --link }
    if {$bex_quote} { lappend cmdlist --quote }
    foreach tok [tokenize_command $bex_cmd] {
        lappend cmdlist $tok
    }

    clear_output
    append_output "Preview: [join $cmdlist " "]"
    append_output "---"
    .statusbar configure -text "Expanding commands..."
    update idletasks

    set code [catch {exec {*}$cmdlist 2>@1} result]
    if {$result ne ""} {
        append_output $result
    }
    if {$code != 0} {
        append_output "\n--- ERROR ---"
        .statusbar configure -text "Expansion failed. Check your command syntax."
    } else {
        set nlines [llength [split [string trim $result] "\n"]]
        .statusbar configure -text "Preview complete: $nlines commands would be generated."
    }
}

proc submitBatch {} {
    global bex_cmd bex_dryrun

    set cmdlist [build_batch_cmd]
    if {$cmdlist eq ""} { return }

    if {$bex_dryrun} { lappend cmdlist --dry-run }

    # Append separator and the user command tokens (properly tokenized)
    lappend cmdlist --
    foreach tok [tokenize_command $bex_cmd] {
        lappend cmdlist $tok
    }

    # Confirm unless dry-run
    if {!$bex_dryrun} {
        set answer [tk_messageBox -icon question -type yesno \
            -title "Confirm Submission" \
            -message "Submit the following batch job?\n\n[join $cmdlist " "]"]
        if {$answer eq "no"} {
            return
        }
    }

    clear_output
    append_output "Running: [join $cmdlist " "]"
    append_output "---"
    .statusbar configure -text "Submitting..."
    update idletasks

    set code [catch {exec {*}$cmdlist 2>@1} result]
    if {$result ne ""} {
        append_output $result
    }
    if {$code != 0} {
        append_output "\n--- ERROR ---"
        .statusbar configure -text "Error during submission."
    } else {
        if {$bex_dryrun} {
            .statusbar configure -text "Dry run complete. Review output above."
        } else {
            .statusbar configure -text "Batch job submitted successfully."
        }
    }
}

proc addArg {} {
    global bex_cmd bex_helper_opt bex_helper_vals
    set opt [string trim $bex_helper_opt]
    set vals [string trim $bex_helper_vals]
    if {$vals eq ""} {
        error_box "Values cannot be empty."
        return
    }
    # Wrap values in brackets unless user already included them
    if {[string match {\[*} $vals] && [string match {*\]} $vals]} {
        set valtok $vals
    } else {
        set valtok "\[$vals\]"
    }
    set parts {}
    if {$opt ne ""} { lappend parts $opt }
    lappend parts $valtok
    if {[string trim $bex_cmd] eq ""} {
        set bex_cmd [join $parts " "]
    } else {
        append bex_cmd " " [join $parts " "]
    }
    set bex_helper_opt ""
    set bex_helper_vals ""
}

# Center window
update idletasks
set w [winfo reqwidth .]
set h [winfo reqheight .]
set sw [winfo screenwidth .]
set sh [winfo screenheight .]
set x [expr {($sw - $w)/2}]
set y [expr {($sh - $h)/3}]
wm geometry . +$x+$y
