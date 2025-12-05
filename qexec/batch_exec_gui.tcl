#!/usr/bin/env wish
# batch_exec_gui.tcl - A minimal Tcl/Tk front-end for batch_exec.sh

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

# --- GUI Layout ---
wm title . "batch_exec GUI"

frame .options -borderwidth 2 -relief groove
pack .options -padx 8 -pady 8 -fill both -expand 1

grid columnconfigure .options 1 -weight 1
grid columnconfigure .options 3 -weight 1

label .options.lbl_cmd -text {Base command (use [..] for expansion):}
entry .options.ent_cmd -textvariable bex_cmd -width 70
grid .options.lbl_cmd -row 0 -column 0 -columnspan 4 -sticky w -padx 4 -pady 2
grid .options.ent_cmd -row 1 -column 0 -columnspan 4 -sticky ew -padx 4 -pady 4

label .options.lbl_time -text "Time (hrs):"
entry .options.ent_time -textvariable bex_time -width 8
label .options.lbl_nodes -text "Nodes / array size:"
entry .options.ent_nodes -textvariable bex_nodes -width 8
grid .options.lbl_time  -row 2 -column 0 -sticky w -padx 4 -pady 2
grid .options.ent_time  -row 2 -column 1 -sticky w -padx 4 -pady 2
grid .options.lbl_nodes -row 2 -column 2 -sticky w -padx 4 -pady 2
grid .options.ent_nodes -row 2 -column 3 -sticky w -padx 4 -pady 2

label .options.lbl_ncpus -text "CPUs per task:"
entry .options.ent_ncpus -textvariable bex_ncpus -width 8
label .options.lbl_jobs -text "Jobs per node (GNU parallel):"
entry .options.ent_jobs -textvariable bex_jobs -width 8
grid .options.lbl_ncpus -row 3 -column 0 -sticky w -padx 4 -pady 2
grid .options.ent_ncpus -row 3 -column 1 -sticky w -padx 4 -pady 2
grid .options.lbl_jobs  -row 3 -column 2 -sticky w -padx 4 -pady 2
grid .options.ent_jobs  -row 3 -column 3 -sticky w -padx 4 -pady 2

label .options.lbl_mem -text "Memory (e.g., 6G):"
entry .options.ent_mem -textvariable bex_mem -width 10
label .options.lbl_name -text "Job name:"
entry .options.ent_name -textvariable bex_name -width 15
grid .options.lbl_mem  -row 4 -column 0 -sticky w -padx 4 -pady 2
grid .options.ent_mem  -row 4 -column 1 -sticky w -padx 4 -pady 2
grid .options.lbl_name -row 4 -column 2 -sticky w -padx 4 -pady 2
grid .options.ent_name -row 4 -column 3 -sticky w -padx 4 -pady 2

label .options.lbl_account -text "Account:"
entry .options.ent_account -textvariable bex_account -width 15
label .options.lbl_logdir -text "Log dir:"
entry .options.ent_logdir -textvariable bex_logdir -width 25
grid .options.lbl_account -row 5 -column 0 -sticky w -padx 4 -pady 2
grid .options.ent_account -row 5 -column 1 -sticky w -padx 4 -pady 2
grid .options.lbl_logdir -row 5 -column 2 -sticky w -padx 4 -pady 2
grid .options.ent_logdir -row 5 -column 3 -sticky ew -padx 4 -pady 2

checkbutton .options.chk_link  -text "Link mode (zip args)" -variable bex_link
checkbutton .options.chk_quote -text "Quote tokens"        -variable bex_quote
checkbutton .options.chk_dry   -text "Dry run only"        -variable bex_dryrun
grid .options.chk_link  -row 6 -column 0 -columnspan 2 -sticky w -padx 4 -pady 2
grid .options.chk_quote -row 6 -column 2 -sticky w -padx 4 -pady 2
grid .options.chk_dry   -row 6 -column 3 -sticky w -padx 4 -pady 2

label .options.help -text {Example: myprog -a [1,2,3] --flag [x,y] --opt file:[/tmp/list.txt]} \
    -anchor w -justify left
grid .options.help -row 7 -column 0 -columnspan 4 -sticky w -padx 4 -pady 6

# Arg helper frame
frame .arghelper -borderwidth 2 -relief groove
pack .arghelper -padx 8 -pady 4 -fill x
label .arghelper.lbl -text {Argument helper (optional): enter option (e.g., -a or --foo) and values list; click "Add" to append to the command above. Values will be wrapped in [...] automatically unless you include brackets yourself.}
grid .arghelper.lbl -row 0 -column 0 -columnspan 3 -sticky w -padx 4 -pady 4
label .arghelper.lopt -text "Option (optional):"
entry .arghelper.eopt -textvariable bex_helper_opt -width 15
label .arghelper.lval -text "Values (comma/range/file: etc.):"
entry .arghelper.eval -textvariable bex_helper_vals -width 40
button .arghelper.add -text "Add Arg" -command addArg
grid .arghelper.lopt -row 1 -column 0 -sticky w -padx 4 -pady 2
grid .arghelper.eopt -row 1 -column 1 -sticky w -padx 4 -pady 2
grid .arghelper.lval -row 2 -column 0 -sticky w -padx 4 -pady 2
grid .arghelper.eval -row 2 -column 1 -sticky w -padx 4 -pady 2
grid .arghelper.add -row 2 -column 2 -sticky ew -padx 4 -pady 2

frame .buttons
pack .buttons -side bottom -fill x -padx 8 -pady 6
button .buttons.submit -text "Submit" -command submitBatch
button .buttons.quit   -text "Quit"   -command exit
pack .buttons.quit -side right -padx 4
pack .buttons.submit -side right -padx 4

label .status -text "Ready." -anchor w -justify left
pack .status -side bottom -fill x -padx 8 -pady 4

# --- Submission logic ---
proc submitBatch {} {
    global bex_cmd bex_time bex_nodes bex_ncpus bex_mem bex_jobs \
           bex_name bex_account bex_logdir bex_link bex_quote bex_dryrun

    if {[string trim $bex_cmd] eq ""} {
        error_box "Base command cannot be empty."
        return
    }
    if {![string is integer -strict $bex_time] || $bex_time <= 0} {
        error_box "Time must be a positive integer (hours)."
        return
    }
    foreach {val label} [list $bex_nodes "nodes" $bex_ncpus "CPUs" $bex_jobs "jobs"] {
        if {![string is integer -strict $val] || $val <= 0} {
            error_box "[string totitle $label] must be a positive integer."
            return
        }
    }
    if {[string trim $bex_mem] ne ""} {
        if {![regexp {^[0-9]+[KMG]$} [string toupper $bex_mem]]} {
            error_box "Memory must look like 6G, 512M, etc."
            return
        }
    }

    set script_path [find_script batch_exec.sh]
    if {$script_path eq ""} {
        error_box "batch_exec.sh not found next to GUI or in PATH."
        return
    }

    set cmdlist [list $script_path --time $bex_time --nodes $bex_nodes --ncpus $bex_ncpus --jobs $bex_jobs]
    if {[string trim $bex_mem] ne ""} { lappend cmdlist --mem [string toupper $bex_mem] }
    if {[string trim $bex_name] ne ""} { lappend cmdlist --name $bex_name }
    if {[string trim $bex_account] ne ""} { lappend cmdlist --account $bex_account }
    if {[string trim $bex_logdir] ne ""} { lappend cmdlist --log-dir $bex_logdir }
    if {$bex_link} { lappend cmdlist --link }
    if {$bex_quote} { lappend cmdlist --quote }
    if {$bex_dryrun} { lappend cmdlist --dry-run }

    # Append separator and the user command tokens
    lappend cmdlist -- {*}[split $bex_cmd]

    set cmdline [join $cmdlist " "]
    .status configure -text "Running: $cmdline"
    update idletasks

    set output ""
    set code [catch {set output [eval exec $cmdlist]} errmsg]
    if {$code != 0} {
        error_box "Failed: $errmsg\n$output"
        .status configure -text "Error."
        return
    }
    info_box "Submitted" $output
    .status configure -text "Done."
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

# Center window roughly
update
set w [winfo reqwidth .]
set h [winfo reqheight .]
set sw [winfo screenwidth .]
set sh [winfo screenheight .]
set x [expr {($sw - $w)/2}]
set y [expr {($sh - $h)/3}]
wm geometry . +$x+$y
