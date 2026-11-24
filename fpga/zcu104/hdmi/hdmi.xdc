# ZCU104 pins for the HDMI TX test design (UG1267 v1.1, Tables 3-22, 3-26, 3-27 and the clock tables)
set_property -dict {PACKAGE_PIN H11 IOSTANDARD LVDS DIFF_TERM_ADV TERM_100} [get_ports clk125_p]
set_property -dict {PACKAGE_PIN G11 IOSTANDARD LVDS DIFF_TERM_ADV TERM_100} [get_ports clk125_n]
create_clock -period 8.000 -name clk125 [get_ports clk125_p]
# HDMI_DRU_CLOCK 156.25 MHz into quad 226 MGTREFCLK1
set_property PACKAGE_PIN U10 [get_ports gt_refclk_p]
set_property PACKAGE_PIN U9  [get_ports gt_refclk_n]
create_clock -period 6.400 -name gt_refclk [get_ports gt_refclk_p]
# HDMI_TX0..2 (GTHE4_CHANNEL_X0Y16..18)
set_property PACKAGE_PIN M4 [get_ports {hdmi_tx_p[0]}]
set_property PACKAGE_PIN M3 [get_ports {hdmi_tx_n[0]}]
set_property PACKAGE_PIN L6 [get_ports {hdmi_tx_p[1]}]
set_property PACKAGE_PIN L5 [get_ports {hdmi_tx_n[1]}]
set_property PACKAGE_PIN K4 [get_ports {hdmi_tx_p[2]}]
set_property PACKAGE_PIN K3 [get_ports {hdmi_tx_n[2]}]
# TMDS clock (HDMI_TX_LVDS_OUT) and the retimer's output enable and hot-plug detect
set_property -dict {PACKAGE_PIN H9 IOSTANDARD LVDS} [get_ports hdmi_clk_p]
set_property -dict {PACKAGE_PIN G9 IOSTANDARD LVDS} [get_ports hdmi_clk_n]
set_property -dict {PACKAGE_PIN A2 IOSTANDARD LVCMOS33} [get_ports hdmi_tx_en]
set_property -dict {PACKAGE_PIN E3 IOSTANDARD LVCMOS33} [get_ports hdmi_hpd]
# user LEDs 0 and 3 (the other two are in a bank the board file marks as 3.3 V on a 1.8 V pin)
set_property -dict {PACKAGE_PIN D5 IOSTANDARD LVCMOS33} [get_ports {led[0]}]
set_property -dict {PACKAGE_PIN B5 IOSTANDARD LVCMOS33} [get_ports {led[1]}]
# the 25 MHz free-running clock, the transmitter user clock and the 78 MHz pixel clock are separate domains; crossings are synchronised in the wizard or static
set_false_path -from [get_ports hdmi_hpd]
