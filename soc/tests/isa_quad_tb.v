// Runs one riscv-test on the quad-core SoC: all four harts start at 0x8000_0000, the test's entry code parks harts 1-3 (mhartid != 0),
// hart 0 runs the test. Plusargs: +HEX=<words file, word 0 at 0x8000_0000> +TOHOST=<hex address> +LIMIT=<cycles>. The test ends when the
// word at tohost is written (1 is a pass; any other value is a failure, value>>1 is the failing check). Prints PASS or FAIL.
`ifdef PS2
`define PS2TIE , .ps2k_clk_i(1'b1), .ps2k_dat_i(1'b1), .ps2m_clk_i(1'b1), .ps2m_dat_i(1'b1)
`else
`define PS2TIE
`endif
module isa_quad_tb;
`include "memview.vh"
  reg clk = 0, rst = 1;
  reg meip = 0, rx_valid = 0, s2 = 0, s3 = 0;
  reg [7:0] rx_data = 0;
  wire uart_irq, uart_tx_valid;
  wire [7:0] uart_tx_data;
  reg [1023:0] hexfile;
  reg [31:0] tohost_addr;
  integer limit, cyc, done;
  reg [31:0] v, dump_a;
  integer dump_n, k;
`ifdef PERIPH
  top dut (.clk(clk), .rst(rst), .rx_valid(rx_valid), .rx_data(rx_data), .ext_s2(s2), .ext_s3(s3), .meip(meip),
           .uart_irq(uart_irq), .uart_tx_valid(uart_tx_valid), .uart_tx_data(uart_tx_data),
           .gpio_in(16'd0), .spi_miso(1'b0), .i2c_scl_i(1'b1), .i2c_sda_i(1'b1) `PS2TIE);
`else
  top dut (.clk(clk), .rst(rst), .rx_valid(rx_valid), .rx_data(rx_data), .ext_s2(s2), .ext_s3(s3), .meip(meip), .periph_rdata(32'd0),
           .uart_irq(uart_irq), .uart_tx_valid(uart_tx_valid), .uart_tx_data(uart_tx_data));
`endif
  always #5 clk = ~clk;
  reg rlog = 0;   // +RETLOG: hart 0's write-back stage, one line per instruction that leaves it (pc, word, privilege, exception flag and cause)
  initial rlog = $test$plusargs("RETLOG");
  always @(posedge clk) if (rlog && !rst && dut.u_c0_core_gate.en && dut.u_c0_trap_unit.valid)
    $display("RET %h %h p%0d x%0d c%0h mprv%0d mpp%0d sum%0d mxr%0d tval%h", dut.u_c0_trap_unit.pc, dut.u_c0_trap_unit.inst, dut.u_c0_trap_unit.priv, dut.u_c0_trap_unit.xcpt | dut.u_c0_trap_unit.irq, dut.u_c0_trap_unit.cause, dut.u_c0_mstatus_reg.mprv, dut.u_c0_mstatus_reg.mpp, dut.u_c0_mstatus_reg.sum, dut.u_c0_mstatus_reg.mxr, dut.u_c0_trap_unit.tval);
  always @(posedge clk) if (rlog && !rst && dut.u_c0_perm_check_d.fault && dut.u_c0_tlb_d.hit && dut.u_c0_xlate_on.xlate_d)
    $display("PERMFAULT kind%0d dpriv%0d sum%0d mxr%0d flags%b va%h", dut.u_c0_perm_check_d.kind, dut.u_c0_perm_check_d.priv, dut.u_c0_perm_check_d.sum, dut.u_c0_perm_check_d.mxr, dut.u_c0_perm_check_d.flags, dut.u_c0_tlb_d.va);
  always @(posedge clk) if (rlog && !rst && dut.u_c0_ptw.req && dut.u_c0_ptw.grant) $display("PTE a=%h pte=%h fault=%b", dut.u_c0_ptw.addr, dut.u_c0_ptw.rdata, dut.u_c0_ptw.fault);
  reg pf_prev = 0;
  always @(posedge clk) if (rlog && !rst && dut.u_c0_ptw.fault !== pf_prev) begin pf_prev = dut.u_c0_ptw.fault; $display("PTWFAULT %b vpn=%h acc=%b", pf_prev, dut.u_c0_ptw.fault_vpn, dut.u_c0_ptw.fault_access); end
  reg [127:0] pcfg_prev = 0;
  always @(posedge clk) if (rlog && !rst && dut.u_c0_pmp_regs16.cfg_all !== pcfg_prev) begin pcfg_prev = dut.u_c0_pmp_regs16.cfg_all; $display("PMPCFG %h addr0..3 %h %h %h %h", pcfg_prev[31:0], dut.u_c0_pmp_regs16.addr_all[31:0], dut.u_c0_pmp_regs16.addr_all[63:32], dut.u_c0_pmp_regs16.addr_all[95:64], dut.u_c0_pmp_regs16.addr_all[127:96]); end
  always @(posedge clk) if (rlog && !rst && dut.u_c0_pmp_check_ilo.deny) $display("PMPDENY_I pa=%h priv=%0d", dut.u_c0_pmp_check_ilo.pa, dut.u_c0_pmp_check_ilo.priv);
  reg trlog = 0; reg [31:0] pm_epc = 0, pm_cause = 0;   // +TRAPLOG: hart 0's machine trap CSRs whenever mepc or mcause changes
  initial trlog = $test$plusargs("TRAPLOG");
  always @(posedge clk) if (trlog && (dut.u_c0_csr_mregs.mepc !== pm_epc || dut.u_c0_csr_mregs.mcause !== pm_cause)) begin
    pm_epc = dut.u_c0_csr_mregs.mepc; pm_cause = dut.u_c0_csr_mregs.mcause;
    $display("TRAP mcause=%h mepc=%h mtval=%h", pm_cause, pm_epc, dut.u_c0_csr_mregs.mtval);
  end
  always @(posedge clk) if (uart_tx_valid) $write("%c", uart_tx_data);   // the test's console output (ACT4 failure messages)
  initial begin
    if (!$value$plusargs("HEX=%s", hexfile)) begin $display("FAIL no HEX"); $finish; end
    if (!$value$plusargs("TOHOST=%h", tohost_addr)) tohost_addr = 32'h80001000;
    if (!$value$plusargs("LIMIT=%d", limit)) limit = 400000;
    #1;
    $readmemh(hexfile, dut.u_ram_main.u_ip.mem);
    repeat (3) @(posedge clk);
    rst <= 0;   // non-blocking: the core must still see reset at this edge
    done = 0;
    for (cyc = 0; cyc < limit && !done; cyc = cyc + 1) begin
      @(posedge clk);
      v = `RAMW((tohost_addr - 32'h80000000) >> 2);
      if (v != 0) done = 1;
    end
    if (!done) $display("FAIL timeout after %0d cycles, tohost still 0", cyc);
    else if (v == 32'd1) $display("PASS in %0d cycles", cyc);
    else $display("FAIL tohost=%0d (check %0d) after %0d cycles", v, v >> 1, cyc);
    if ($value$plusargs("DUMPA=%h", dump_a) && $value$plusargs("DUMPN=%d", dump_n))
      for (k = 0; k < dump_n; k = k + 1) $display("DUMP %08x %08x", dump_a + 4 * k, `RAMW(((dump_a - 32'h80000000) >> 2) + k));
    $finish;
  end
endmodule
