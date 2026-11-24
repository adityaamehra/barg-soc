# Program the HDMI test design and print the VIO status.   vivado -mode batch -source vio_read.tcl [-tclargs <name=value> ...]   (name=value sets a VIO output first, e.g. vio_pol=7)
set root [file normalize [pwd]]
open_hw_manager
connect_hw_server -url localhost:3121 -quiet
open_hw_target -quiet
set dev [lindex [get_hw_devices xczu*] 0]
current_hw_device $dev
if {[lsearch $argv -noprogram] < 0} {
  set_property PROGRAM.FILE $root/build/hdmi_tx.bit $dev
  set_property PROBES.FILE $root/build/hdmi_tx.ltx $dev
  set_property FULL_PROBES.FILE $root/build/hdmi_tx.ltx $dev
  program_hw_devices $dev
}
refresh_hw_device $dev
set vio [lindex [get_hw_vios] 0]
proc probe {name} { return [get_property INPUT_VALUE [get_hw_probes $name -of_objects [lindex [get_hw_vios] 0]]] }
foreach a $argv {
  if {[regexp {^(\w+)=(\w+)$} $a -> n v]} {
    set p [get_hw_probes -of_objects $vio -filter "NAME =~ *$n*"]
    set_property OUTPUT_VALUE $v $p
    commit_hw_vio $p
  }
}
after 500
refresh_hw_vio $vio
foreach p [get_hw_probes -of_objects $vio] { puts "VIO [get_property NAME $p] = [get_property INPUT_VALUE $p][get_property OUTPUT_VALUE $p]" }
