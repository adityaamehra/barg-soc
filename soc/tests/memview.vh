// The memory as the cores see it, for the testbenches: with the cache hierarchy (HIER: the netlist has the last-level cache array u_l3_array) a word
// may sit dirty in the last-level cache and not yet in the external memory model, so a test result is read from the cache first. Included inside the
// testbench module; RAMW(i) is the word with index i (from 0x8000_0000). Writes by a testbench to the memory model are not seen by the caches.
`ifdef HIER
  function [31:0] coh_word(input [31:0] wi);
    reg [31:0] a, r;
    reg found;
    integer w, line;
    begin
      a = 32'h80000000 + (wi << 2);
      found = 1'b0; r = 32'd0;
      for (w = 0; w < 16; w = w + 1) begin
        line = a[12:5] * 16 + w;
        if (!found && dut.u_l3_array.u_ip.valid_q[line] && dut.u_l3_array.u_ip.tag_q[line] == a[31:13]) begin
          found = 1'b1; r = dut.u_l3_array.u_ip.data_q[line][a[4:2] * 32 +: 32];
        end
      end
      coh_word = found ? r : dut.u_ram_main.u_ip.mem[wi];
    end
  endfunction
  `define RAMW(i) coh_word(i)
  // A testbench write that the caches see: the memory model's word, the word in the last-level cache if it holds the line, and the line dropped
  // from the two L2 arrays and the four data caches (they are write-through and never hold the only copy).
  task coh_poke(input [31:0] wi, input [31:0] v);
    reg [31:0] a;
    integer w, line;
    begin
      a = 32'h80000000 + (wi << 2);
      dut.u_ram_main.u_ip.mem[wi] = v;
      for (w = 0; w < 16; w = w + 1) begin
        line = a[12:5] * 16 + w;
        if (dut.u_l3_array.u_ip.valid_q[line] && dut.u_l3_array.u_ip.tag_q[line] == a[31:13]) dut.u_l3_array.u_ip.data_q[line][a[4:2] * 32 +: 32] = v;
      end
      for (w = 0; w < 8; w = w + 1) begin
        line = a[11:5] * 8 + w;
        if (dut.u_l2_array_a.u_ip.valid_q[line] && dut.u_l2_array_a.u_ip.tag_q[line] == a[31:12]) dut.u_l2_array_a.u_ip.valid_q[line] = 1'b0;
        if (dut.u_l2_array_b.u_ip.valid_q[line] && dut.u_l2_array_b.u_ip.tag_q[line] == a[31:12]) dut.u_l2_array_b.u_ip.valid_q[line] = 1'b0;
      end
      for (w = 0; w < 2; w = w + 1) begin
        line = a[12:5] * 2 + w;
        if (dut.u_c0_dcache.u_ip.valid_q[line] && dut.u_c0_dcache.u_ip.tag_q[line] == a[31:13]) dut.u_c0_dcache.u_ip.valid_q[line] = 1'b0;
        if (dut.u_c1_dcache.u_ip.valid_q[line] && dut.u_c1_dcache.u_ip.tag_q[line] == a[31:13]) dut.u_c1_dcache.u_ip.valid_q[line] = 1'b0;
        if (dut.u_c2_dcache.u_ip.valid_q[line] && dut.u_c2_dcache.u_ip.tag_q[line] == a[31:13]) dut.u_c2_dcache.u_ip.valid_q[line] = 1'b0;
        if (dut.u_c3_dcache.u_ip.valid_q[line] && dut.u_c3_dcache.u_ip.tag_q[line] == a[31:13]) dut.u_c3_dcache.u_ip.valid_q[line] = 1'b0;
      end
    end
  endtask
  `define RAMPOKE(i, v) coh_poke(i, v)
`else
  `define RAMW(i) dut.u_ram_main.u_ip.mem[i]
  `define RAMPOKE(i, v) dut.u_ram_main.u_ip.mem[i] = (v)
`endif
