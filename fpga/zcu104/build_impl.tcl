# Implementation only (synthesis kept), with congestion-friendly directives, then the bitstream and reports.   vivado -mode batch -source build_impl.tcl
set root [file normalize [pwd]]
open_project $root/build/vivado/soc.xpr
set_property STEPS.PLACE_DESIGN.ARGS.DIRECTIVE AltSpreadLogic_high [get_runs impl_1]
set_property STEPS.PHYS_OPT_DESIGN.IS_ENABLED true [get_runs impl_1]
set_property STEPS.ROUTE_DESIGN.ARGS.DIRECTIVE Explore [get_runs impl_1]
set_property STEPS.WRITE_BITSTREAM.TCL.PRE [file normalize $root/constraints/pre_bit.tcl] [get_runs impl_1]
reset_run impl_1
launch_runs impl_1 -to_step write_bitstream -jobs 16
wait_on_run impl_1
open_run impl_1
file mkdir $root/build/out
report_timing_summary -file $root/build/out/timing_impl.rpt
report_utilization -file $root/build/out/util_impl.rpt
file copy -force $root/build/vivado/soc.runs/impl_1/design_1_wrapper.bit $root/build/out/soc.bit
puts "IMPL DONE"
