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
set qexec_account "rrg-brad" ;# Default account
set qexec_omp_threads "1"
set qexec_interactive 0 ;# 0 for false, 1 for true
set qexec_nox11 0       ;# 0 for false, 1 for true


# --- GUI Layout ---
wm title . "qexec.sh GUI"
# Center the window later

# Frame for options
frame .options -borderwidth 2 -relief groove
pack .options -padx 5 -pady 5 -fill x -expand yes

# Configure grid columns for weights (allow resizing)
grid columnconfigure .options 1 -weight 1
grid columnconfigure .options 3 -weight 1

# Command Entry (Row 0)
label .options.lbl_cmd -text "Command:"
entry .options.ent_cmd -textvariable qexec_command -width 60
grid .options.lbl_cmd -row 0 -column 0 -sticky w -padx 2 -pady 2
grid .options.ent_cmd -row 0 -column 1 -columnspan 3 -sticky ew -padx 2 -pady 2

# Time & CPUs (Row 1)
label .options.lbl_time -text "Time (hrs):"
entry .options.ent_time -textvariable qexec_time -width 8
label .options.lbl_ncpus -text "CPUs:"
entry .options.ent_ncpus -textvariable qexec_ncpus -width 8
grid .options.lbl_time   -row 1 -column 0 -sticky w -padx 2 -pady 2
grid .options.ent_time   -row 1 -column 1 -sticky w -padx 2 -pady 2
grid .options.lbl_ncpus  -row 1 -column 2 -sticky w -padx 2 -pady 2
grid .options.ent_ncpus  -row 1 -column 3 -sticky w -padx 2 -pady 2

# Memory & Nodes (Row 2)
label .options.lbl_mem -text "Memory (e.g., 6G):"
entry .options.ent_mem -textvariable qexec_mem -width 10
label .options.lbl_nodes -text "Nodes:"
entry .options.ent_nodes -textvariable qexec_nodes -width 8
grid .options.lbl_mem    -row 2 -column 0 -sticky w -padx 2 -pady 2
grid .options.ent_mem    -row 2 -column 1 -sticky w -padx 2 -pady 2
grid .options.lbl_nodes  -row 2 -column 2 -sticky w -padx 2 -pady 2
grid .options.ent_nodes  -row 2 -column 3 -sticky w -padx 2 -pady 2

# Job Name & Array (Row 3)
label .options.lbl_name -text "Job Name:"
entry .options.ent_name -textvariable qexec_job_name -width 20
label .options.lbl_array -text "Array (e.g., 1-10):"
entry .options.ent_array -textvariable qexec_array -width 15
grid .options.lbl_name   -row 3 -column 0 -sticky w -padx 2 -pady 2
grid .options.ent_name   -row 3 -column 1 -sticky ew -padx 2 -pady 2
grid .options.lbl_array  -row 3 -column 2 -sticky w -padx 2 -pady 2
grid .options.ent_array  -row 3 -column 3 -sticky ew -padx 2 -pady 2

# Account & OMP Threads (Row 4)
label .options.lbl_account -text "Account:"
entry .options.ent_account -textvariable qexec_account -width 20
label .options.lbl_omp -text "OMP Threads:"
entry .options.ent_omp -textvariable qexec_omp_threads -width 8
grid .options.lbl_account -row 4 -column 0 -sticky w -padx 2 -pady 2
grid .options.ent_account -row 4 -column 1 -sticky ew -padx 2 -pady 2
grid .options.lbl_omp     -row 4 -column 2 -sticky w -padx 2 -pady 2
grid .options.ent_omp     -row 4 -column 3 -sticky w -padx 2 -pady 2

# Checkboxes (Row 5)
checkbutton .options.chk_interactive -text "Interactive Job" -variable qexec_interactive -command toggleCommandEntry
checkbutton .options.chk_nox11 -text "Disable X11" -variable qexec_nox11
grid .options.chk_interactive -row 5 -column 0 -columnspan 2 -sticky w -padx 2 -pady 2
grid .options.chk_nox11       -row 5 -column 2 -columnspan 2 -sticky w -padx 2 -pady 2


# Frame for buttons
frame .buttons
pack .buttons -padx 5 -pady 5 -fill x

# Submit Button
button .buttons.submit -text "Submit Job" -command submitJob
button .buttons.quit -text "Quit" -command exit
pack .buttons.quit -side right -padx 5
pack .buttons.submit -side right -padx 5


# --- Procedures ---

# Toggle command entry state based on interactive checkbox
proc toggleCommandEntry {} {
    global qexec_interactive
    if {$qexec_interactive} {
        .options.ent_cmd configure -state disabled
    } else {
        .options.ent_cmd configure -state normal
    }
}

# Submit Procedure
proc submitJob {} {
    global qexec_command qexec_time qexec_ncpus qexec_nodes qexec_mem \
           qexec_job_name qexec_array qexec_account qexec_omp_threads \
           qexec_interactive qexec_nox11

    # Find the qexec.sh script (adjust path if necessary)
    # Assumes qexec.sh is in the same directory or in PATH
    set qexec_script "./qexec.sh" ;# Or provide full path /path/to/qexec.sh

    # Basic check if qexec.sh exists and is executable
    if {![file exists $qexec_script] || ![file executable $qexec_script]} {
         tk_messageBox -icon error -type ok -title "Error" \
             -message "qexec.sh not found or not executable at:\n$qexec_script\nPlease check the path in qexec_gui.tcl."
         return
    }

    # Base command list
    set cmd_list [list $qexec_script]

    # --- Add options based on GUI values ---

    # Interactive Flag
    if {$qexec_interactive} {
        lappend cmd_list "-i"
    }

    # Time
    if {[string trim $qexec_time] ne ""} {
        # Allow HH:MM:SS or just hours (integer) - basic check
        if {([string is integer -strict $qexec_time] && $qexec_time > 0) || \
            [regexp {^[0-9]+:[0-5][0-9]:[0-5][0-9]$} $qexec_time] || \
            [regexp {^[0-9]+-[0-9]+:[0-5][0-9]:[0-5][0-9]$} $qexec_time]} {
             lappend cmd_list "-t" $qexec_time
        } else {
            tk_messageBox -icon error -type ok -title "Error" -message "Invalid Time format. Use hours (e.g., 1), HH:MM:SS, or D-HH:MM:SS."
            return
        }
    } else {
         tk_messageBox -icon error -type ok -title "Error" -message "Time cannot be empty."
         return
    }

    # CPUs
    if {[string trim $qexec_ncpus] ne ""} {
        if {[string is integer -strict $qexec_ncpus] && $qexec_ncpus > 0} {
             lappend cmd_list "-n" $qexec_ncpus
        } else {
            tk_messageBox -icon error -type ok -title "Error" -message "CPUs must be a positive integer."
            return
        }
    }

    # Nodes
    if {[string trim $qexec_nodes] ne ""} {
        if {[string is integer -strict $qexec_nodes] && $qexec_nodes > 0} {
             lappend cmd_list "--nodes" $qexec_nodes
        } else {
            tk_messageBox -icon error -type ok -title "Error" -message "Nodes must be a positive integer."
            return
        }
    }

    # Memory (Optional)
    if {[string trim $qexec_mem] ne ""} {
        if {[regexp {^[0-9]+[KMG]$} [string toupper $qexec_mem]]} {
             lappend cmd_list "-m" [string toupper $qexec_mem]
        } else {
             tk_messageBox -icon error -type ok -title "Error" -message "Memory must be like '6G', '512M', '1024K', etc."
             return
        }
    }

    # Job Name (Optional)
    if {[string trim $qexec_job_name] ne ""} {
        lappend cmd_list "-j" $qexec_job_name
    }

    # Array (Optional)
    if {[string trim $qexec_array] ne ""} {
         # Regex allows formats like 1, 1-5, 1-10%2
        if {[regexp {^[0-9]+((-[0-9]+)?(%[0-9]+)?)?(,[0-9]+((-[0-9]+)?(%[0-9]+)?))*$} $qexec_array]} {
            lappend cmd_list "-a" $qexec_array
        } else {
             tk_messageBox -icon error -type ok -title "Error" -message "Invalid Array format. Use e.g., 1-5, 1,3,5, 1-10%2."
             return
        }
    }

    # Account
    if {[string trim $qexec_account] ne ""} {
        lappend cmd_list "--account" $qexec_account
    } else {
         tk_messageBox -icon error -type ok -title "Error" -message "Account cannot be empty."
         return
    }

    # OMP Threads
    if {[string trim $qexec_omp_threads] ne ""} {
        if {[string is integer -strict $qexec_omp_threads] && $qexec_omp_threads > 0} {
             lappend cmd_list "-o" $qexec_omp_threads
        } else {
            tk_messageBox -icon error -type ok -title "Error" -message "OMP Threads must be a positive integer."
            return
        }
    }

    # NoX11 Flag
    if {$qexec_nox11} {
        lappend cmd_list "--nox11"
    }

    # Add the command itself if not interactive
    if {!$qexec_interactive} {
        if {[string trim $qexec_command] eq ""} {
            tk_messageBox -icon error -type ok -title "Error" -message "Command cannot be empty for batch jobs."
            return
        }
        # Use -- to separate options from the command
         lappend cmd_list "--" $qexec_command
    }

    # --- Execution ---

    # Display the command to be executed
    if {[tk_messageBox -icon question -type yesno -title "Confirm Submission" \
        -message "Submit the following job?\n\n[join $cmd_list " "]"] eq "no"} {
        return
    }

    puts "Executing: [join $cmd_list " "]"

    # Create a simple status window
    toplevel .status
    wm title .status "Job Status"
    label .status.lbl -text "Submitting job..." -padx 10 -pady 5
    pack .status.lbl

    # Execute the command in the background to keep GUI responsive
    # Using 'catch' to handle potential errors during execution
    if {[catch {exec {*}$cmd_list >@ stdout &} pid]} {
        # Error launching
        destroy .status
        tk_messageBox -icon error -type ok -title "Launch Error" -message "Error executing qexec.sh:\n$pid"
    } else {
        # Launched successfully, update status
        .status.lbl configure -text "Job submitted via qexec.sh (PID: $pid).\nCheck SLURM queue (squeue) for status."
        button .status.ok -text "OK" -command {destroy .status}
        pack .status.ok -pady 5
        puts "qexec.sh launched with PID: $pid"
    }
}

# --- Main Setup & Loop ---

# Initialize command entry state
toggleCommandEntry

# Center the window
update idletasks ; # Ensure window size is calculated
set sw [winfo screenwidth .]
set sh [winfo screenheight .]
set w [winfo reqwidth .]
set h [winfo reqheight .]
set x [expr {($sw - $w) / 2}]
set y [expr {($sh - $h) / 2}]
wm geometry . +$x+$y

tkwait window . 