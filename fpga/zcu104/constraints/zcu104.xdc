# ZCU104 pins: UART and LEDs from the Vivado board file (zcu104 1.1); PMOD pins from the ZCU104 master constraints (UG1267), cross-checked against PMOD0_0 = G8 in the guide.
# Console: the board's USB-UART (CP2108 channel 2, PL side). tx/rx are from the FPGA's side, as in the board file's interface.
set_property -dict {PACKAGE_PIN C19 IOSTANDARD LVCMOS18} [get_ports uart_txd_0]
set_property -dict {PACKAGE_PIN A20 IOSTANDARD LVCMOS18} [get_ports uart_rxd_0]
# status: two of the four user LEDs (gpu_diverged, uart irq); LED 1 and 2 are in a high-performance bank the board file calls LVCMOS33, which is not legal, so those two outputs are left unplaced
set_property -dict {PACKAGE_PIN D5 IOSTANDARD LVCMOS33} [get_ports {status_0[0]}]
set_property -dict {PACKAGE_PIN B5 IOSTANDARD LVCMOS33} [get_ports {status_0[3]}]
# PMOD0 / PMOD1 (bank 87, 3.3 V): pins from the ZCU104 master constraints (UG1267; PMOD0_0 = G8 also appears in the guide's pin table). Plain set_property lines only (xdc has no foreach).
# PS/2 on PMOD0_0..3 (open drain in the wrapper; PS/2 devices are 5 V parts: use a level shifter and pull-ups)
set_property -dict {PACKAGE_PIN G8 IOSTANDARD LVCMOS33} [get_ports ps2k_clk_0]
set_property -dict {PACKAGE_PIN H8 IOSTANDARD LVCMOS33} [get_ports ps2k_dat_0]
set_property -dict {PACKAGE_PIN G7 IOSTANDARD LVCMOS33} [get_ports ps2m_clk_0]
set_property -dict {PACKAGE_PIN H7 IOSTANDARD LVCMOS33} [get_ports ps2m_dat_0]
# video: hsync, vsync, rgb332 (bit 0 = blue LSB) on PMOD0_4..7 and PMOD1_0..5 (resistor-ladder DAC to a VGA connector)
set_property -dict {PACKAGE_PIN G6 IOSTANDARD LVCMOS33} [get_ports vid_hsync_0]
set_property -dict {PACKAGE_PIN H6 IOSTANDARD LVCMOS33} [get_ports vid_vsync_0]
set_property -dict {PACKAGE_PIN J6 IOSTANDARD LVCMOS33} [get_ports {vid_rgb332_0[0]}]
set_property -dict {PACKAGE_PIN J7 IOSTANDARD LVCMOS33} [get_ports {vid_rgb332_0[1]}]
set_property -dict {PACKAGE_PIN J9 IOSTANDARD LVCMOS33} [get_ports {vid_rgb332_0[2]}]
set_property -dict {PACKAGE_PIN K9 IOSTANDARD LVCMOS33} [get_ports {vid_rgb332_0[3]}]
set_property -dict {PACKAGE_PIN K8 IOSTANDARD LVCMOS33} [get_ports {vid_rgb332_0[4]}]
set_property -dict {PACKAGE_PIN L8 IOSTANDARD LVCMOS33} [get_ports {vid_rgb332_0[5]}]
set_property -dict {PACKAGE_PIN L10 IOSTANDARD LVCMOS33} [get_ports {vid_rgb332_0[6]}]
set_property -dict {PACKAGE_PIN M10 IOSTANDARD LVCMOS33} [get_ports {vid_rgb332_0[7]}]
# clock tree: the ungated clock (clk_core) and the cores' gated clocks are all BUFGCE outputs of the PS clock; one delay group so the router matches their insertion delays
set_property CLOCK_DELAY_GROUP soc_clks [get_nets -hier -quiet -filter {NAME =~ *clk_core || NAME =~ *gclk}]
