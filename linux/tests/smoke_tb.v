module smoke_tb;
  reg clk = 0, rst = 1;
  reg [31:0] prog [0:15];
  integer i, cycles;
  wire [31:0] fpa_lo, fpa_hi, mem_alu, mem_sd, dmem_wd, wb_y, va_i, va_hi, va_d, walk_va_w;
  wire [2:0] mtype; wire [1:0] msrc; wire mvalid, mxcpt, mwrite, mkill, dwe, req_w, rset, rclr, sfen, mstall, wstart;
  wire [21:0] satp;
  reg [31:0] inst_lo_r, inst_hi_r;
  top u (
    .clk(clk), .rst(rst), .hartid(2'd0), .memory_read(32'd0), .ext_msip(1'b0), .ext_mtip(1'b0), .ext_meip(1'b0),
    .sel_ram(1'b0), .ram_we(1'b0), .is_io(1'b0), .io_raw(32'd0), .rsv_valid(1'b0), .rsv_addr(32'd0),
    .mem_alu_y(mem_alu), .mem_store_data(mem_sd), .mem_memtype(mtype), .mem_memsrc(msrc), .mem_valid(mvalid),
    .mem_xcpt(mxcpt), .mem_write(mwrite), .mem_kill(mkill), .dmem_we(dwe), .dmem_wdata(dmem_wd), .req(req_w),
    .rsv_set(rset), .rsv_clr(rclr), .satp_ppn(satp), .sfence(sfen), .mtime(64'd0),
    .fetch_pa_lo(fpa_lo), .fetch_pa_hi(fpa_hi), .inst_lo(inst_lo_r), .inst_hi(inst_hi_r), .va_ilo(va_i), .va_ihi(va_hi),
    .tlb_ilo_hit(1'b0), .tlb_ilo_ppa(20'd0), .tlb_ilo_flags(8'd0), .tlb_ihi_hit(1'b0), .tlb_ihi_ppa(20'd0), .tlb_ihi_flags(8'd0),
    .tlb_d_hit(1'b0), .tlb_d_ppa(20'd0), .tlb_d_flags(8'd0), .ptw_busy(1'b0), .ptw_fault(1'b0), .ptw_fault_access(1'b0),
    .ptw_fault_vpn(20'd0), .va_d(va_d), .mmu_stall(mstall), .walk_start(wstart), .walk_va(walk_va_w));
  always #5 clk = ~clk;
  // the instruction memory (the tile's job): words at 0x8000_0000, reads at the physical fetch addresses
  always @* begin
    inst_lo_r = prog[(fpa_lo - 32'h80000000) >> 2];
    inst_hi_r = prog[((fpa_lo + 4) - 32'h80000000) >> 2];
  end
  initial begin
    for (i = 0; i < 16; i = i + 1) prog[i] = 32'h0000006F;       // jal x0, 0 (spin)
    prog[0] = 32'h00500093;   // addi x1, x0, 5
    prog[1] = 32'h00700113;   // addi x2, x0, 7
    prog[2] = 32'h002081B3;   // add  x3, x1, x2
    prog[3] = 32'h00302023;   // sw   x3, 0(x0)
    cycles = 0;
    repeat (3) @(posedge clk);
    rst <= 0;   // non-blocking: the core must still see reset at this edge
    repeat (60) begin
      @(negedge clk);
      cycles = cycles + 1;
      if (mwrite) $display("cycle %0d: store addr %h data %h memtype %b", cycles, mem_alu, mem_sd, mtype);
      if (mxcpt) $display("cycle %0d: exception on memory stage", cycles);
    end
    $display("pc-side fetch address now %h", fpa_lo);
    $finish;
  end
endmodule
