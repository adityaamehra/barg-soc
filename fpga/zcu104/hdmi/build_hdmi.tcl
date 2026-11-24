# Vivado batch flow for the HDMI TX test design:  cd demos/fpga/zcu104/hdmi ; vivado -mode batch -source build_hdmi.tcl   ->  build/hdmi_tx.bit
set root [file normalize [pwd]]
set proj $root/build/vivado
create_project hdmi $proj -part xczu7ev-ffvc1156-2-e -force
create_ip -name gtwizard_ultrascale -vendor xilinx.com -library ip -module_name hdmi_gt
set ip [get_ips hdmi_gt]
set_property -dict [list CONFIG.GT_DIRECTION BOTH CONFIG.CHANNEL_ENABLE {X0Y16 X0Y17 X0Y18} CONFIG.TX_MASTER_CHANNEL X0Y16 CONFIG.RX_MASTER_CHANNEL X0Y16 \
  CONFIG.TX_PLL_TYPE CPLL CONFIG.TX_LINE_RATE 0.78125 CONFIG.TX_REFCLK_FREQUENCY 156.25 CONFIG.TX_REFCLK_SOURCE {X0Y16 clk1-1 X0Y17 clk1-1 X0Y18 clk1-1} \
  CONFIG.RX_PLL_TYPE CPLL CONFIG.RX_LINE_RATE 0.78125 CONFIG.RX_REFCLK_FREQUENCY 156.25 CONFIG.RX_REFCLK_SOURCE {X0Y16 clk1-1 X0Y17 clk1-1 X0Y18 clk1-1} \
  CONFIG.TX_DATA_ENCODING RAW CONFIG.TX_USER_DATA_WIDTH 20 CONFIG.TX_INT_DATA_WIDTH 20 CONFIG.RX_USER_DATA_WIDTH 20 CONFIG.RX_INT_DATA_WIDTH 20 \
  CONFIG.FREERUN_FREQUENCY 25 CONFIG.LOCATE_TX_USER_CLOCKING CORE CONFIG.LOCATE_COMMON CORE \
  CONFIG.ENABLE_OPTIONAL_PORTS {cpllrefclksel_in gtsouthrefclk1_in txoutclk_out cplllock_out txpolarity_in txdiffctrl_in}] $ip
generate_target all $ip
create_ip -name vio -vendor xilinx.com -library ip -module_name vio_hdmi
set_property -dict [list CONFIG.C_NUM_PROBE_IN 7 CONFIG.C_NUM_PROBE_OUT 4 \
  CONFIG.C_PROBE_IN0_WIDTH 1 CONFIG.C_PROBE_IN1_WIDTH 1 CONFIG.C_PROBE_IN2_WIDTH 1 CONFIG.C_PROBE_IN3_WIDTH 3 CONFIG.C_PROBE_IN4_WIDTH 3 CONFIG.C_PROBE_IN5_WIDTH 3 CONFIG.C_PROBE_IN6_WIDTH 1 \
  CONFIG.C_PROBE_OUT0_WIDTH 3 CONFIG.C_PROBE_OUT1_WIDTH 1 CONFIG.C_PROBE_OUT2_WIDTH 1 CONFIG.C_PROBE_OUT3_WIDTH 4 \
  CONFIG.C_PROBE_OUT0_INIT_VAL 0x0 CONFIG.C_PROBE_OUT1_INIT_VAL 0x1 CONFIG.C_PROBE_OUT2_INIT_VAL 0x0 CONFIG.C_PROBE_OUT3_INIT_VAL 0xC] [get_ips vio_hdmi]
generate_target all [get_ips vio_hdmi]
add_files [list $root/tmds_enc2.v $root/hdmi_stream.v $root/hdmi_tx_top.v]
add_files -fileset constrs_1 $root/hdmi.xdc
set_property top hdmi_tx_top [current_fileset]
update_compile_order -fileset sources_1
launch_runs synth_1 -jobs 8
wait_on_run synth_1
open_run synth_1
file mkdir $root/build
report_utilization -file $root/build/util_synth.rpt
launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1
open_run impl_1
report_timing_summary -file $root/build/timing.rpt
report_clock_utilization -file $root/build/clocks.rpt
file copy -force $proj/hdmi.runs/impl_1/hdmi_tx_top.bit $root/build/hdmi_tx.bit
write_debug_probes -force $root/build/hdmi_tx.ltx
puts "HDMI BIT DONE"
