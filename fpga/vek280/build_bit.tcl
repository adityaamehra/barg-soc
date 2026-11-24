# Synthesis, implementation and device image (.pdi) of build/vivado/soc.xpr (made by build_bd.tcl); copies the .pdi and .xsa to build/out/.
set root [file normalize [pwd]]
open_project $root/build/vivado/soc.xpr
reset_run synth_1
launch_runs synth_1 -jobs 16
wait_on_run synth_1
open_run synth_1
file mkdir $root/build/out
report_utilization -file $root/build/out/util_synth.rpt
reset_run impl_1
launch_runs impl_1 -to_step write_device_image -jobs 16
wait_on_run impl_1
open_run impl_1
report_timing_summary -file $root/build/out/timing_impl.rpt
report_utilization -file $root/build/out/util_impl.rpt
file copy -force [glob $root/build/vivado/soc.runs/impl_1/design_1_wrapper*.pdi] $root/build/out/soc.pdi
write_hw_platform -fixed -include_bit -force $root/build/out/soc.xsa
puts "PDI DONE"
