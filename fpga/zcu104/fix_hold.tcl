# Post-route hold fixing on the routed checkpoint of build_bit.tcl, then a new bitstream.   vivado -mode batch -source fix_hold.tcl
set root [file normalize [pwd]]
open_checkpoint $root/build/vivado/soc.runs/impl_1/design_1_wrapper_routed.dcp
source $root/constraints/pre_bit.tcl
report_timing_summary -delay_type min_max -file $root/build/out/timing_before_fix.rpt
phys_opt_design -hold_fix
report_timing_summary -file $root/build/out/timing_after_fix1.rpt
set wns_h [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
puts "HOLD after -hold_fix: $wns_h"
if {$wns_h < 0} { phys_opt_design -hold_fix -aggressive_hold_fix; set wns_h [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]; puts "HOLD after aggressive: $wns_h" }
set wns_s [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
puts "SETUP: $wns_s"
report_timing_summary -file $root/build/out/timing_fixed.rpt
report_route_status
write_checkpoint -force $root/build/out/soc_fixed.dcp
write_bitstream -force $root/build/out/soc_fixed.bit
puts "FIX DONE hold=[get_property SLACK [get_timing_paths -delay_type min -max_paths 1]] setup=[get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]"
