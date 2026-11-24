// Testbench of the quad-core SoC (the CPU-only build) with a console: the UART's transmitter prints on the terminal and the terminal feeds the
// UART's receiver through DPI-C (host.cpp). A byte is offered only when the UART's 16-byte receive FIFO has room (fewer than 12 bytes in it),
// so nothing is lost however fast the terminal types or pastes. Plusargs: +HEX=<words file, word 0 at 0x8000_0000>, +LIMIT=<cycles>.
`ifdef PS2
`include "ps2_device.vh"
`endif
module console_tb;
  import "DPI-C" function void host_init();
  import "DPI-C" function int host_getc();
  import "DPI-C" function void host_putc(input int c);
  import "DPI-C" function int host_quit();
  import "DPI-C" function int host_ps2_byte(input int dev);
  import "DPI-C" function void host_finish(input longint cycles);
  import "DPI-C" function void host_checkpoint(input longint cycles);
  import "DPI-C" function int host_ckpt_framedir_len();
  import "DPI-C" function int host_ckpt_framedir_ch(input int i);
  import "DPI-C" function longint host_ckpt_frame_every();
  import "DPI-C" function longint host_ckpt_flags();
  import "DPI-C" function longint host_ckpt_next();
  reg clk = 0, rst = 1;
  reg meip = 0, rx_valid = 0, s2 = 0, s3 = 0;
  reg [7:0] rx_data = 0;
  wire uart_irq, uart_tx_valid, periph_we, periph_re;
`ifdef PS2
  // the PS/2 keyboard and mouse: open-drain lines; bytes for the host come from <BARG_PS2_DIR>/kbd.in and mouse.in (host.cpp)
  wire ps2k_clk_low, ps2k_dat_low, ps2m_clk_low, ps2m_dat_low, ps2k_clk_i, ps2k_dat_i, ps2m_clk_i, ps2m_dat_i;
  ps2_device #(.MOUSE(0)) u_kbd (.clk(clk), .rst(rst), .host_clk_low(ps2k_clk_low), .host_dat_low(ps2k_dat_low), .clk_line(ps2k_clk_i), .dat_line(ps2k_dat_i));
  ps2_device #(.MOUSE(1)) u_mouse (.clk(clk), .rst(rst), .host_clk_low(ps2m_clk_low), .host_dat_low(ps2m_dat_low), .clk_line(ps2m_clk_i), .dat_line(ps2m_dat_i));
`define PS2CONN , .ps2k_clk_i(ps2k_clk_i), .ps2k_dat_i(ps2k_dat_i), .ps2k_clk_low(ps2k_clk_low), .ps2k_dat_low(ps2k_dat_low), .ps2m_clk_i(ps2m_clk_i), .ps2m_dat_i(ps2m_dat_i), .ps2m_clk_low(ps2m_clk_low), .ps2m_dat_low(ps2m_dat_low)
`else
`define PS2CONN
`endif
`ifdef PERIPH
`include "periph_models.vh"
`define PCONN .gpio_in(gpio_in), .gpio_out(gpio_out), .gpio_oe(gpio_oe), .spi_miso(spi_mosi), .spi_sclk(spi_sclk), .spi_mosi(spi_mosi), .spi_cs_n(spi_cs_n), .i2c_scl_i(scl), .i2c_sda_i(sda), .i2c_scl_o(i2c_scl_o), .i2c_sda_o(i2c_sda_o), .bus_addr(bus_addr), .bus_wdata(bus_wdata) `PS2CONN
`else
`define PCONN .periph_rdata(32'd0), .periph_we(periph_we), .periph_re(periph_re), .bus_addr(bus_addr), .bus_wdata(bus_wdata)
`endif
  wire [7:0] uart_tx_data;
  wire [31:0] bus_addr, bus_wdata;
`include "memview.vh"
  // +DMBASE=<first word index> +DMCOUNT=<count>: at the end of the run, those RAM words (read through the caches) as "[mem] index value" on stderr, e.g. the kernel's log buffer
  longint dm_base = 0, dm_count = 0; integer dmi;
  task dump_mem;
    begin
      if ($value$plusargs("DMBASE=%d", dm_base) && $value$plusargs("DMCOUNT=%d", dm_count))
        for (dmi = 0; dmi < dm_count; dmi = dmi + 1) $fwrite(32'h80000002, "[mem] %0d %h\n", dm_base + dmi, `RAMW(dm_base + dmi));
    end
  endtask
  longint cyc, limit, next_rx, frame_every, ckpt_at;
  integer fseq;
  integer c;
  reg [1023:0] hexfile;
`ifdef GPU
  // the build with the GPU cluster: the GPU's status and video pins are outputs; +FRAMES=<dir> dumps core 0's video memory when the run ends
  wire gpu_running, gpu_done, gpu_error, gpu_diverged, gpu_hsync, gpu_vsync, gpu_de;
  wire [15:0] gpu_rgb;
  top dut (.clk(clk), .rst(rst), .rx_valid(rx_valid), .rx_data(rx_data), .ext_s2(s2), .ext_s3(s3), .meip(meip),
           .uart_irq(uart_irq), .uart_tx_valid(uart_tx_valid), .uart_tx_data(uart_tx_data),
           `PCONN,
           .gpu_running(gpu_running), .gpu_done(gpu_done), .gpu_error(gpu_error), .gpu_diverged(gpu_diverged), .gpu_hsync(gpu_hsync),
           .gpu_vsync(gpu_vsync), .gpu_de(gpu_de), .gpu_rgb(gpu_rgb));
  reg [1023:0] framedir;
  reg [2047:0] fn;
  reg have_frames = 0;
  task dump_frames;
    begin
      if (have_frames) begin
        $sformat(fn, "%0s/f0_0.hex", framedir); $writememh(fn, dut.u_u_gpu0__vwbank0.mem);
        $sformat(fn, "%0s/f0_1.hex", framedir); $writememh(fn, dut.u_u_gpu0__vwbank1.mem);
        $sformat(fn, "%0s/f0_2.hex", framedir); $writememh(fn, dut.u_u_gpu0__vwbank2.mem);
        $sformat(fn, "%0s/f0_3.hex", framedir); $writememh(fn, dut.u_u_gpu0__vwbank3.mem);
        $sformat(fn, "%0s/seq", framedir); fseq = $fopen(fn, "w"); $fdisplay(fseq, "%0d", cyc); $fclose(fseq);   // written last: a new frame is complete
      end
    end
  endtask
  // after a run is resumed from a checkpoint (host_checkpoint): the new run's frame directory and rate
  task ckpt_attach;
    integer k, n;
    reg [1023:0] t;
    begin
      n = host_ckpt_framedir_len();
      if (n > 1 || (n == 1 && host_ckpt_framedir_ch(0) != 45)) begin   // a directory name ("-" means none)
        t = 0;
        for (k = 0; k < n; k = k + 1) t = {t[1015:0], host_ckpt_framedir_ch(k)[7:0]};
        framedir = t; have_frames = 1;
      end
      if (host_ckpt_frame_every() > 0) frame_every = host_ckpt_frame_every();
      if (host_ckpt_next() > 0) ckpt_at = host_ckpt_next();   // a resumed run can park the next checkpoint (a later cycle, its own directory)
    end
  endtask
`else
  top dut (.clk(clk), .rst(rst), .rx_valid(rx_valid), .rx_data(rx_data), .ext_s2(s2), .ext_s3(s3), .meip(meip),
           .gpu_rdata(32'd0), .uart_irq(uart_irq), .uart_tx_valid(uart_tx_valid), .uart_tx_data(uart_tx_data),
           `PCONN);
  task dump_frames; begin end endtask
  task ckpt_attach; begin end endtask
`endif
  always #5 clk = ~clk;
  always @(posedge clk) if (uart_tx_valid) host_putc(uart_tx_data);
  // +STAMP: the cycle count at the end of every console line, on stderr (for timing runs: the same firmware text appears at the same point of every build)
  reg stamp = 0;
  initial stamp = $test$plusargs("STAMP");
  // +PCS: the four fetch addresses every 2^22 cycles, on stderr (where is each hart when the console is silent?)
  // +WARP: simulation-only time skip. While all four harts sit in WFI with nothing pending, the CLINT's time jumps to just before the earliest timer compare,
  // so the simulator does not spend cycles on the kernel's idle waits (like QEMU's -icount sleep=off). The SoC itself is unchanged.
  // +TICKDIV=N: the timebase (CLINT mtime) advances once every N core cycles instead of every cycle (a real SoC's core runs several times faster than its 10 MHz
  // timebase). Simulation-side prescaler: the testbench takes back N-1 of every N increments. The SoC itself is unchanged.
  integer tickdiv = 1, tickcnt = 0;
  initial void'($value$plusargs("TICKDIV=%d", tickdiv));
  always @(negedge clk) if (!rst && tickdiv > 1) begin
    tickcnt = tickcnt + 1;
    if (tickcnt >= tickdiv) tickcnt = 0;
    else dut.u_clint4.mtime_reg = dut.u_clint4.mtime_reg - 64'd1;
  end
  reg warp = 0;
  longint warp_skipped = 0;
  reg [63:0] w_min;
  initial warp = $test$plusargs("WARP");
  always @(negedge clk) if (warp && !rst && dut.u_c0_wfi_wake.hold && dut.u_c1_wfi_wake.hold && dut.u_c2_wfi_wake.hold && dut.u_c3_wfi_wake.hold) begin
    w_min = dut.u_clint4.mtimecmp_reg[0];
    if (dut.u_clint4.mtimecmp_reg[1] < w_min) w_min = dut.u_clint4.mtimecmp_reg[1];
    if (dut.u_clint4.mtimecmp_reg[2] < w_min) w_min = dut.u_clint4.mtimecmp_reg[2];
    if (dut.u_clint4.mtimecmp_reg[3] < w_min) w_min = dut.u_clint4.mtimecmp_reg[3];
    if (w_min > dut.u_clint4.mtime_reg + 64'd64 && w_min < 64'hFFFFFFFF00000000) begin
      warp_skipped = warp_skipped + (w_min - 64'd8 - dut.u_clint4.mtime_reg);
      dut.u_clint4.mtime_reg = w_min - 64'd8;
    end
  end
  // +UARTMON: report a UART register write that stays asserted for two or more consecutive cycles (a store applied again while its hart waits)
  reg uartmon = 0; integer uw_run = 0; integer uw_prints = 0;
  initial uartmon = $test$plusargs("UARTMON");
  always @(posedge clk) if (uartmon && !rst) begin
    if (dut.u_uart16550.we) begin
      uw_run = uw_run + 1;
      if (uw_run == 2 && uw_prints < 4) begin uw_prints = uw_prints + 1; $display("UARTWR-REPEAT cyc=%0d addr=%h wdata=%h en=%b%b%b%b pst=%b arb_state=%0d cur=%0d grant=%b%b%b%b go=%b%b%b%b wdone=%b eng_ready=%b", cyc, dut.u_uart16550.addr, dut.u_uart16550.wdata, dut.u_c0_core_gate.en, dut.u_c1_core_gate.en, dut.u_c2_core_gate.en, dut.u_c3_core_gate.en, dut.u_postw.pst, dut.u_mem_arb.state, dut.u_mem_arb.cur, dut.u_mem_arb.grant0, dut.u_mem_arb.grant1, dut.u_mem_arb.grant2, dut.u_mem_arb.grant3, dut.u_postw.go0, dut.u_postw.go1, dut.u_postw.go2, dut.u_postw.go3, dut.u_mem_arb.wdone, dut.u_mem_arb.eng_ready); end
    end else uw_run = 0;
  end
  reg pcs = 0;
  initial pcs = $test$plusargs("PCS");
  // +PCFINE=<cycle>: from that cycle on, hart 0's fetch address every 4096 cycles (to see which functions the silent kernel spends its time in)
  longint pcfine = -1;
  initial if (!$value$plusargs("PCFINE=%d", pcfine)) pcfine = -1;
  always @(posedge clk) if (pcfine >= 0 && cyc >= pcfine && (cyc & 4095) == 0) $fwrite(32'h80000002, "[pc] %h %h %h %h\n", dut.u_c0_pc.pc, dut.u_c1_pc.pc, dut.u_c2_pc.pc, dut.u_c3_pc.pc);
  // +PCS also logs the CLINT: every write (kind, hart, data) and every change of the four software-interrupt lines
  integer nclint = 0; reg [3:0] msip_prev = 0;
  always @(posedge clk) if (pcs) begin
    if (dut.u_clint4.we && nclint < 300) begin nclint = nclint + 1; $fwrite(32'h80000002, "[clint] cyc=%0d kind=%0d hart=%0d wdata=%h\n", cyc, dut.u_clint4.kind, dut.u_clint4.hart, dut.u_clint4.wdata); end
    if ({dut.u_clint4.msip3, dut.u_clint4.msip2, dut.u_clint4.msip1, dut.u_clint4.msip0} !== msip_prev) begin
      msip_prev = {dut.u_clint4.msip3, dut.u_clint4.msip2, dut.u_clint4.msip1, dut.u_clint4.msip0}; $fwrite(32'h80000002, "[msip] cyc=%0d %b\n", cyc, msip_prev);
    end
  end
  // +PCS: which traps hart 0 takes (interrupt flag and cause), counted per 4M-cycle window: [traps] i<cause> = interrupts, x<cause> = exceptions
  integer th [0:31]; integer thi; integer claim0 = 0, claimn = 0;
  always @(posedge clk) if (pcs && !rst && dut.u_plic4.re && dut.u_plic4.addr[25:2] == 24'h80401) begin if (dut.u_plic4.rdata == 0) claim0 = claim0 + 1; else claimn = claimn + 1; end
  initial for (thi = 0; thi < 32; thi = thi + 1) th[thi] = 0;
  always @(posedge clk) if (pcs && !rst) begin
    if (dut.u_c0_core_gate.en && dut.u_c0_trap_unit.valid && dut.u_c0_trap_unit.xcpt) th[{dut.u_c0_trap_unit.irq, dut.u_c0_trap_unit.cause}] = th[{dut.u_c0_trap_unit.irq, dut.u_c0_trap_unit.cause}] + 1;
    if ((cyc & 4194303) == 0 && cyc > 0) begin
      $fwrite(32'h80000002, "[traps %0d]", cyc);
      for (thi = 0; thi < 32; thi = thi + 1) if (th[thi] != 0) begin $fwrite(32'h80000002, " %s%0d=%0d", thi >= 16 ? "i" : "x", thi & 15, th[thi]); th[thi] = 0; end
      $fwrite(32'h80000002, " | kbd irq=%b mouse irq=%b | plic s1..s5=%b%b%b%b%b seip0=%b claimS: zero=%0d id=%0d | kbd fifo=%0d re=%b mouse fifo=%0d | mip_sw=%h mie=%h mideleg=%h mip=%h insvc4,5=%b%b en1=%b\n", dut.u_ps2k_ctl.irq, dut.u_ps2m_ctl.irq,
              dut.u_plic4.s1, dut.u_plic4.s2, dut.u_plic4.s3, dut.u_plic4.s4, dut.u_plic4.s5, dut.u_plic4.seip0, claim0, claimn, dut.u_ps2k_fifo.count, dut.u_ps2k_ctl.re_reg, dut.u_ps2m_fifo.count, dut.u_c0_csr_mregs.mip_sw, dut.u_c0_csr_mregs.mie, dut.u_c0_csr_mregs.mideleg, dut.u_c0_mip_merge.mip, dut.u_plic4.in_service[4], dut.u_plic4.in_service[5], dut.u_plic4.enable[1]);
      claim0 = 0; claimn = 0;
    end
  end
  // instructions that left the pipeline on hart 0 (valid in the write-back stage at each edge of the gated clock) and gated-clock edges: CPI = cycles / retired
  longint nret0 = 0, nedge0 = 0;
  always @(posedge dut.u_c0_core_gate.gclk) if (pcs && !rst) begin nedge0 = nedge0 + 1; if (dut.u_c0_mem_wb.valid_out) nret0 = nret0 + 1; end
  // +FREEZE123: harts 1 to 3 never run (their clock gates stay off): an experiment on how much the parked harts slow hart 0 down
  initial if ($test$plusargs("FREEZE123")) begin
    force dut.u_c1_core_gate.en = 1'b0; force dut.u_c2_core_gate.en = 1'b0; force dut.u_c3_core_gate.en = 1'b0;
  end
  // cycles hart 0 spends waiting, by cause (a cycle can count under more than one): translation (page-table walk), instruction-fetch miss, data-cache miss (memory builds only)
  longint wait_mmu = 0, wait_imiss = 0, wait_dmiss = 0;
`ifdef MEMSYS
  // memory-engine transactions started per hart (and how many of them are atomics' reads / stores / line refills): who uses the engine
  longint eng_n [0:3]; longint eng_st [0:3]; longint eng_ln [0:3]; integer ek;
  initial for (ek = 0; ek < 4; ek = ek + 1) begin eng_n[ek] = 0; eng_st[ek] = 0; eng_ln[ek] = 0; end
  always @(posedge clk) if (pcs && !rst && dut.u_mem_arb.eng_start) begin
    ek = dut.u_mem_arb.sel0 ? 0 : dut.u_mem_arb.sel1 ? 1 : dut.u_mem_arb.sel2 ? 2 : 3;
    eng_n[ek] = eng_n[ek] + 1; if (dut.u_mem_arb.eng_we) eng_st[ek] = eng_st[ek] + 1; if (dut.u_mem_arb.eng_line) eng_ln[ek] = eng_ln[ek] + 1;
  end
  always @(posedge clk) if (pcs && (cyc & 16777215) == 0 && cyc > 0) $fwrite(32'h80000002, "[eng %0d] h0=%0d/%0d/%0d h1=%0d/%0d/%0d h2=%0d/%0d/%0d h3=%0d/%0d/%0d (all/writes/lines)\n", cyc,
    eng_n[0], eng_st[0], eng_ln[0], eng_n[1], eng_st[1], eng_ln[1], eng_n[2], eng_st[2], eng_ln[2], eng_n[3], eng_st[3], eng_ln[3]);
  // counts: plain stores of hart 0 that completed, page-table walks (rising edges of the translation wait); with the L3: write hits and write misses (write-around)
  longint n_store = 0, n_walk = 0, n_l3wr = 0, n_l3wm = 0, n_l3rd = 0; reg mmu_prev = 0; reg [3:0] l3st_prev = 0;
  always @(posedge clk) if (pcs && !rst) begin
    if (dut.u_c0_dcache_ctl.wdone && dut.u_c0_dcache_ctl.self && dut.u_c0_dcache_ctl.w_plain) n_store = n_store + 1;
    if (dut.u_c0_dc_hold.a && !mmu_prev) n_walk = n_walk + 1;
    mmu_prev = dut.u_c0_dc_hold.a;
`ifdef HIER
    if (dut.u_l3_ctl.state == 4'd7 && l3st_prev != 4'd7) n_l3wr = n_l3wr + 1;
    if (dut.u_l3_ctl.state == 4'd8 && l3st_prev != 4'd8) n_l3wm = n_l3wm + 1;
    if (dut.u_l3_ctl.state == 4'd1 && l3st_prev == 4'd0 && !dut.u_l3_ctl.we_q) n_l3rd = n_l3rd + 1;
    l3st_prev = dut.u_l3_ctl.state;
`endif
  end
  always @(posedge clk) if (warp && (cyc & 16777215) == 0 && cyc > 0) $fwrite(32'h80000002, "[warp %0d] skipped=%0d\n", cyc, warp_skipped);
  always @(posedge clk) if (pcs && (cyc & 16777215) == 0 && cyc > 0) $fwrite(32'h80000002, "[cnt %0d] stores=%0d walks=%0d l3_write_hit=%0d l3_write_miss=%0d l3_reads=%0d\n", cyc, n_store, n_walk, n_l3wr, n_l3wm, n_l3rd);
  // cycles with the core's clock off, by the first cause that applies: translation, instruction-fetch miss, data miss, plain RAM store, atomic, device access, other
  longint off_total = 0, off_mmu = 0, off_imiss = 0, off_dmiss = 0, off_store = 0, off_amo = 0, off_io = 0, off_other = 0, off_wfi = 0;
  always @(posedge clk) if (pcs && !rst && !dut.u_c0_core_gate.en) begin
    off_total = off_total + 1;
    if (dut.u_c0_dc_hold.a) off_mmu = off_mmu + 1;
    else if (dut.u_c0_dc_hold.b) off_imiss = off_imiss + 1;
    else if (dut.u_c0_dcache_ctl.dmiss) off_dmiss = off_dmiss + 1;
    else if (dut.u_c0_dcache_ctl.req && dut.u_c0_dcache_ctl.is_amo) off_amo = off_amo + 1;
    else if (dut.u_c0_dcache_ctl.req && dut.u_c0_dcache_ctl.is_store && dut.u_c0_dcache_ctl.is_ram) off_store = off_store + 1;
    else if (dut.u_c0_dcache_ctl.req && !dut.u_c0_dcache_ctl.is_ram) off_io = off_io + 1;
    else if (dut.u_c0_wfi_wake.hold) off_wfi = off_wfi + 1;
    else off_other = off_other + 1;
  end
  always @(posedge clk) if (pcs && (cyc & 16777215) == 0 && cyc > 0) $fwrite(32'h80000002, "[off %0d] total=%0d mmu=%0d imiss=%0d dmiss=%0d store=%0d amo=%0d io=%0d wfi=%0d other=%0d\n", cyc, off_total, off_mmu, off_imiss, off_dmiss, off_store, off_amo, off_io, off_wfi, off_other);
  always @(posedge clk) if (pcs && !rst) begin
    if (dut.u_c0_dc_hold.a) wait_mmu = wait_mmu + 1;
    if (dut.u_c0_dc_hold.b) wait_imiss = wait_imiss + 1;
    if (dut.u_c0_dcache_ctl.dmiss) wait_dmiss = wait_dmiss + 1;
  end
`endif
  longint ntrap0 = 0; reg [31:0] last_trap0 = 0;
  // trap causes of hart 0 (counted when mcause / scause is written with a new trap: the value or the epc changes)
  longint cm [0:63]; longint cs [0:63];
  reg [31:0] pm_epc = 0, ps_epc = 0; integer ci;
  initial for (ci = 0; ci < 64; ci = ci + 1) begin cm[ci] = 0; cs[ci] = 0; end
  always @(posedge clk) if (pcs) begin
    if (dut.u_c0_csr_mregs.mepc !== pm_epc) begin pm_epc = dut.u_c0_csr_mregs.mepc; cm[{dut.u_c0_csr_mregs.mcause[31], dut.u_c0_csr_mregs.mcause[4:0]}] = cm[{dut.u_c0_csr_mregs.mcause[31], dut.u_c0_csr_mregs.mcause[4:0]}] + 1; end
    if (dut.u_c0_csr_sregs.sepc !== ps_epc) begin ps_epc = dut.u_c0_csr_sregs.sepc; cs[{dut.u_c0_csr_sregs.scause[31], dut.u_c0_csr_sregs.scause[4:0]}] = cs[{dut.u_c0_csr_sregs.scause[31], dut.u_c0_csr_sregs.scause[4:0]}] + 1; end
  end
  always @(posedge clk) if (pcs && (cyc & 16777215) == 0) begin
    for (ci = 0; ci < 64; ci = ci + 1) begin
      if (cm[ci] != 0) $fwrite(32'h80000002, "[cause %0d] M %s%0d = %0d\n", cyc, ci >= 32 ? "int " : "exc ", ci & 31, cm[ci]);
      if (cs[ci] != 0) $fwrite(32'h80000002, "[cause %0d] S %s%0d = %0d\n", cyc, ci >= 32 ? "int " : "exc ", ci & 31, cs[ci]);
    end
  end
  always @(posedge clk) if (pcs && dut.u_c0_pc.trap_redirect) begin ntrap0 = ntrap0 + 1; last_trap0 = dut.u_c0_pc.trap_pc; end
  always @(posedge clk) if (pcs && (cyc & 4194303) == 0) $fwrite(32'h80000002, "[pcs %0d] %h %h %h %h traps0=%0d last_target=%h edges0=%0d ret0=%0d wmmu=%0d wimiss=%0d wdmiss=%0d\n", cyc, dut.u_c0_pc.pc, dut.u_c1_pc.pc, dut.u_c2_pc.pc, dut.u_c3_pc.pc, ntrap0, last_trap0, nedge0, nret0, wait_mmu, wait_imiss, wait_dmiss);
  always @(posedge clk) if (stamp && uart_tx_valid && uart_tx_data == 8'h0a) $fwrite(32'h80000002, "[cycle %0d]\n", cyc);
  initial begin
    if (!$value$plusargs("HEX=%s", hexfile)) begin $display("no +HEX"); $finish; end
    if (!$value$plusargs("LIMIT=%d", limit)) limit = 64'd4000000000;
    if (!$value$plusargs("CKPT=%d", ckpt_at)) ckpt_at = 0;   // +CKPT=N (a multiple of 1024) with BARG_CKPT_DIR: park a copy of the whole simulation at cycle N (host.cpp)
    host_init();
`ifdef GPU
    have_frames = $value$plusargs("FRAMES=%s", framedir);
    if (!$value$plusargs("FRAMEEVERY=%d", frame_every)) frame_every = 0;   // +FRAMEEVERY=N: also dump the video memory every N cycles (for the GUI)
`endif
    $readmemh(hexfile, dut.u_ram_main.u_ip.mem);
    repeat (3) @(posedge clk);
    rst <= 0;   // non-blocking: the core must still see reset at this edge
    next_rx = 0;
    for (cyc = 0; cyc < limit; cyc = cyc + 1) begin
      @(posedge clk);
      rx_valid <= 0;
      if ((cyc & 1023) == 0) begin
        if (host_quit() != 0) begin dump_frames; dump_mem; host_finish(cyc); $finish; end
        if (ckpt_at > 0 && cyc == ckpt_at) begin host_checkpoint(cyc); ckpt_attach; if (host_ckpt_flags() & 1) pcs = 1; end
        if (frame_every > 0 && cyc > 0 && (cyc % frame_every) < 1024) dump_frames;
`ifdef PS2
        if ((cyc & 8191) == 0) begin   // bytes from the GUI for the keyboard and the mouse
          c = host_ps2_byte(0); if (c >= 0) u_kbd.push_ext(c[7:0]);
          c = host_ps2_byte(1); if (c >= 0) u_mouse.push_ext(c[7:0]);
        end
`endif
        if (cyc >= next_rx && dut.u_uart16550.RXCNT < 12) begin   // the UART has a 16-byte receive FIFO; leave room
          c = host_getc();
          if (c >= 0) begin rx_valid <= 1; rx_data <= c[7:0]; next_rx = cyc + 1024; end
        end
      end
    end
    dump_frames;
    dump_mem;
    host_finish(cyc);
    $finish;
  end
endmodule
