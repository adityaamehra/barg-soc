# VEK280 pins from the Vivado board file (vek280 1.2, part0_pins.xml). tx/rx are from the FPGA's side.
# Console: the board's USB-UART, PL side (bank 401, 3.3 V)
set_property -dict {PACKAGE_PIN F31 IOSTANDARD LVCMOS33} [get_ports uart_txd_0]
set_property -dict {PACKAGE_PIN E31 IOSTANDARD LVCMOS33} [get_ports uart_rxd_0]
# status: the four user LEDs (gpu_diverged, gpu_error, gpu_running|done, uart irq), 1.5 V
set_property -dict {PACKAGE_PIN AT12 IOSTANDARD LVCMOS15} [get_ports {status_0[0]}]
set_property -dict {PACKAGE_PIN AT11 IOSTANDARD LVCMOS15} [get_ports {status_0[1]}]
set_property -dict {PACKAGE_PIN AU13 IOSTANDARD LVCMOS15} [get_ports {status_0[2]}]
set_property -dict {PACKAGE_PIN AT13 IOSTANDARD LVCMOS15} [get_ports {status_0[3]}]
# clock tree: the ungated clock (clk_core) and the cores' gated clocks are BUFGCE outputs of the PL clock; one delay group so the router matches their insertion delays
set_property CLOCK_DELAY_GROUP soc_clks [get_nets -hier -quiet -filter {NAME =~ *clk_core || NAME =~ *gclk}]
