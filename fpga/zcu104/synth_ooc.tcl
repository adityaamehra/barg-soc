# Out-of-context synthesis of soc_core (no PS, no pins) for the resource and timing picture.   vivado -mode batch -source synth_ooc.tcl -tclargs <part>
set part [expr {[llength $argv] ? [lindex $argv 0] : "xczu7ev-ffvc1156-2-e"}]
set root [file normalize [pwd]]
file mkdir $root/build/out
read_verilog -sv [glob $root/build/src/*.v]
synth_design -top soc_core -part $part -mode out_of_context -flatten_hierarchy rebuilt -gated_clock_conversion on
create_clock -period 10.0 -name clk [get_ports clk]
report_utilization -file $root/build/out/util_ooc.rpt
report_timing_summary -file $root/build/out/timing_ooc.rpt
puts "OOC DONE"
