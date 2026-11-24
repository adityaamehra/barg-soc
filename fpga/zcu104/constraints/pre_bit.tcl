# Bitstream pre-hook: ports without a pin (PS/2, video: PMOD/FMC locations not set yet) are warnings, not errors.
set_property SEVERITY {Warning} [get_drc_checks {NSTD-1 UCIO-1}]
