# Vivado project for the quad-core Linux SoC on the VEK280 (Versal AI Edge VE2802): CIPS (board preset, PL clock 20 MHz) + AXI NoC (LPDDR4 memory controller) <-> soc_vek280.
#   python3 demos/fpga/vek280/export.py --gpu-cores N ; cd demos/fpga/vek280 ; source ~/Xilinx_ent/2025.2/Vivado/settings64.sh ; vivado -mode batch -source build_bd.tcl
# Needs the Enterprise install with Versal support and a licence for the VE2802 (the kit's voucher).
set freq_mhz 20
set root [file normalize [pwd]]
set proj $root/build/vivado
set_param board.repoPaths [list [file normalize ~/Xilinx/2025.2/data/xhub/boards/XilinxBoardStore/boards/Xilinx]]
create_project soc $proj -part xcve2802-vsvh1760-2MP-e-S -force
set_property board_part xilinx.com:vek280:part0:1.2 [current_project]
add_files [glob $root/build/src/*.v]
set_property file_type SystemVerilog [get_files -filter {NAME =~ *build/src/*.v && NAME !~ *soc_vek280.v}]   ;# the generated blocks use declarations in unnamed blocks and the like (SystemVerilog)
update_compile_order -fileset sources_1
create_bd_design design_1

set cips [create_bd_cell -type ip -vlnv xilinx.com:ip:versal_cips:3.4 cips]
apply_bd_automation -rule xilinx.com:bd_rule:cips -config {board_preset {Yes} boot_config {Custom} configure_noc {Add new AXI NoC} debug_config {JTAG} design_flow {Full System} mc_type {LPDDR} num_mc_ddr {None} num_mc_lpddr {1} pl_clocks {1} pl_resets {1}} $cips
# PL clock for the SoC, and one EMIO GPIO bit as the SoC's run line (0 holds it in reset while the image is loaded)
set_property -dict [list CONFIG.PS_PMC_CONFIG [list PMC_CRP_PL0_REF_CTRL_FREQMHZ $freq_mhz PS_GPIO_EMIO_PERIPHERAL_ENABLE 1 PS_GPIO_EMIO_WIDTH 1]] $cips

# the SoC's AXI4 master is one more slave port of the NoC, to the same LPDDR4 controller
set noc [get_bd_cells axi_noc_0]
set_property -dict [list CONFIG.NUM_SI 7 CONFIG.NUM_CLKS 7] $noc
set_property -dict [list CONFIG.DATA_WIDTH 32 CONFIG.CONNECTIONS {MC_3 {read_bw {500} write_bw {500} read_avg_burst {4} write_avg_burst {4}}} CONFIG.CATEGORY pl] [get_bd_intf_pins axi_noc_0/S06_AXI]
set_property CONFIG.ASSOCIATED_BUSIF S06_AXI [get_bd_pins axi_noc_0/aclk6]

set rst [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_0]
set soc [create_bd_cell -type module -reference soc_vek280 soc_0]
# the CIPS makes 19,999,981 Hz, not exactly 20 MHz: the wrapper's FREQ_HZ parameter follows it
connect_bd_net [get_bd_pins cips/pl0_ref_clk] [get_bd_pins axi_noc_0/aclk6] [get_bd_pins soc_0/aclk] [get_bd_pins rst_0/slowest_sync_clk]
connect_bd_net [get_bd_pins cips/pl0_resetn] [get_bd_pins rst_0/ext_reset_in]
connect_bd_net [get_bd_pins rst_0/peripheral_aresetn] [get_bd_pins soc_0/aresetn]
connect_bd_net [get_bd_pins cips/LPD_GPIO_o] [get_bd_pins soc_0/run]
connect_bd_intf_net [get_bd_intf_pins soc_0/m_axi] [get_bd_intf_pins axi_noc_0/S06_AXI]
foreach p {uart_rxd uart_txd status} { make_bd_pins_external [get_bd_pins soc_0/$p] }   ;# PS/2 and video have no pins on this board without an FMC card: left open
assign_bd_address
validate_bd_design
save_bd_design
make_wrapper -files [get_files $proj/soc.srcs/sources_1/bd/design_1/design_1.bd] -top
add_files -norecurse $proj/soc.gen/sources_1/bd/design_1/hdl/design_1_wrapper.v
set_property top design_1_wrapper [current_fileset]
foreach x [glob -nocomplain $root/constraints/*.xdc] { add_files -fileset constrs_1 $x }
puts "BD DONE"
