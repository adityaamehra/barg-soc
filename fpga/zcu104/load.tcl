# xsdb script: bring up the ZCU104, program the SoC, load the Linux image into DDR, release the SoC.
#   xsdb load.tcl build/out/soc.bit /path/to/fw_payload.bin
# Always a full load (PS, DDR, PL, image): a shortcut that only reprogrammed the PL or only reset the SoC left the Linux boot hung at the framebuffer step.
# Board: SW6 = all ON (JTAG boot mode), USB-JTAG cable connected. The script initialises the PS and the DDR itself
# with psu_init.tcl (taken from soc.xsa), so no SD card or FSBL is needed.
# The SoC console is the PL UART on the board's USB-serial bridge (115200 8N1).
set bit [file normalize [lindex $argv 0]]
set img [file normalize [lindex $argv 1]]
set here [file dirname [file normalize [info script]]]
set xsa  [file join $here build out soc.xsa]
set pinit [file join $here build out psu_init.tcl]
if {![file exists $pinit]} { exec unzip -o -q -j $xsa psu_init.tcl -d [file dirname $pinit] }

connect
catch {jtag targets 1; jtag frequency 30000000}   ;# the FT4232H can clock JTAG at 30 MHz (default 15 MHz): about 20% faster transfers
puts [targets]
# JTAG boot mode: the ARM DAP appears as "APU"/"Cortex-A53" after a system reset
targets -set -nocase -filter {name =~ "*PSU*"}
mwr 0xFFCA0038 0x1FF            ;# CSU: enable the DAP and all PS debug ports
targets -set -nocase -filter {name =~ "*PSU*"}
rst -system
after 2000
targets -set -nocase -filter {name =~ "*PSU*"}
source $pinit
psu_init                        ;# clocks, MIO, DDR controller and PHY
after 1000
puts "DDR trained"
fpga -file $bit                 ;# program the PL (soc.bit)
psu_post_config
psu_ps_pl_isolation_removal     ;# PL is reachable from the PS
after 500
psu_ps_pl_reset_config          ;# PL0 reset released, PL0 clock running
after 500

targets -set -nocase -filter {name =~ "*A53*#0"}
rst -processor -clear-registers   ;# take the core out of reset and halt it so that memory can be written
after 500
# check DDR before loading the image
mwr 0x40000000 0xA5A5F00D
if {[mrd -value 0x40000000] != 0xA5A5F00D} { puts "DDR test FAILED"; exit 1 }
puts "DDR ok, loading $img"
dow -data $img 0x40000000
puts "image loaded, first words:"
mrd 0x40000000 4

# EMIO GPIO is bank 3 of the PS GPIO block (base 0xFF0A0000: DATA_3 0x4C, DIRM_3 0x2C4, OEN_3 0x2C8, ZynqMP register map): bit 0 is the SoC run line
mwr 0xFF0A02C4 0x1
mwr 0xFF0A02C8 0x1
mwr 0xFF0A004C 0x1
puts "SoC released (run=1). Watch the PL UART at 115200 8N1."
