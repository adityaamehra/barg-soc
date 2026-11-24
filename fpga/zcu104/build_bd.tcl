# Vivado project for the quad-core Linux SoC on the ZCU104 (xczu7ev): PS (board preset, PL clock 20 MHz, DDR4 behind HP0) <-> soc_zcu104.
#   python3 demos/fpga/zcu104/export.py ; cd demos/fpga/zcu104 ; vivado -mode batch -source build_bd.tcl
# Not run yet (Vivado is not installed on this machine); written from the nuttx-soc ZCU104 flow and the Vivado 2023/2024 Tcl API.
set freq_mhz 20      ;# placed and routed at 30 MHz the worst path misses by 8 ns (about 24 MHz reachable)
set root [file normalize [pwd]]
set proj $root/build/vivado
set_param board.repoPaths [list [file normalize ~/Xilinx/2025.2/data/xhub/boards/XilinxBoardStore/boards/Xilinx]]
create_project soc $proj -part xczu7ev-ffvc1156-2-e -force
set bp [lindex [lsort [get_board_parts -quiet xilinx.com:zcu104:part0:*]] end]
if {$bp ne ""} { set_property board_part $bp [current_project] } else { puts "WARNING: no ZCU104 board files; the PS preset is not applied" }
add_files [glob $root/build/src/*.v]
set_property file_type SystemVerilog [get_files -filter {NAME =~ *build/src/*.v && NAME !~ *soc_zcu104.v}]   ;# the generated blocks use declarations in unnamed blocks and the like (SystemVerilog)
update_compile_order -fileset sources_1
create_bd_design design_1

set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:3.5 ps_e_0]
if {$bp ne ""} { apply_bd_automation -rule xilinx.com:bd_rule:zynq_ultra_ps_e -config {apply_board_preset "1"} $ps }
set_property -dict [list \
  CONFIG.PSU__USE__M_AXI_GP0 0 CONFIG.PSU__USE__M_AXI_GP1 0 CONFIG.PSU__USE__M_AXI_GP2 0 \
  CONFIG.PSU__USE__S_AXI_GP2 1 CONFIG.PSU__SAXIGP2__DATA_WIDTH 32 \
  CONFIG.PSU__FPGA_PL0_ENABLE 1 CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ $freq_mhz \
  CONFIG.PSU__GPIO_EMIO__PERIPHERAL__ENABLE 1 CONFIG.PSU__GPIO_EMIO__PERIPHERAL__IO 1] $ps

set rst [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_0]
set soc [create_bd_cell -type module -reference soc_zcu104 soc_0]

connect_bd_net [get_bd_pins ps_e_0/pl_clk0] [get_bd_pins ps_e_0/saxihp0_fpd_aclk] [get_bd_pins soc_0/aclk] [get_bd_pins rst_0/slowest_sync_clk]
connect_bd_net [get_bd_pins ps_e_0/pl_resetn0] [get_bd_pins rst_0/ext_reset_in]
connect_bd_net [get_bd_pins rst_0/peripheral_aresetn] [get_bd_pins soc_0/aresetn]
connect_bd_net [get_bd_pins ps_e_0/emio_gpio_o] [get_bd_pins soc_0/run]      ;# EMIO GPIO 0: the loader sets it to 1 after the image is in the DDR
connect_bd_intf_net [get_bd_intf_pins soc_0/m_axi] [get_bd_intf_pins ps_e_0/S_AXI_HP0_FPD]
foreach p {uart_rxd uart_txd ps2k_clk ps2k_dat ps2m_clk ps2m_dat vid_hsync vid_vsync vid_rgb332 status} { make_bd_pins_external [get_bd_pins soc_0/$p] }
assign_bd_address
# the SoC reaches the DDR through the wrapper's 0x4000_0000 window (64 MB)
validate_bd_design
save_bd_design
make_wrapper -files [get_files $proj/soc.srcs/sources_1/bd/design_1/design_1.bd] -top
add_files -norecurse $proj/soc.gen/sources_1/bd/design_1/hdl/design_1_wrapper.v
set_property top design_1_wrapper [current_fileset]
foreach x [glob -nocomplain $root/constraints/*.xdc] { add_files -fileset constrs_1 $x }
puts "BD DONE"
