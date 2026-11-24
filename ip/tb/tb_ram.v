// Self-checking testbench for barg_ram: random byte-enabled writes and reads on every port against a reference array.
// Prints "PASS" or "FAIL <reason>" and finishes. Parameters: DEPTH_W, READ_PORTS, SEED, N (operations).
module tb_ram;
  parameter integer DEPTH_W = 6, READ_PORTS = 1, SEED = 1, N = 4000;
  localparam integer DATA_W = 32, WORDS = 1 << DEPTH_W;
  reg clk = 0;
  reg we = 0;
  reg [3:0] be = 0;
  reg [DEPTH_W-1:0] waddr = 0;
  reg [31:0] wdata = 0;
  reg [READ_PORTS*DEPTH_W-1:0] raddr = 0;
  wire [READ_PORTS*DATA_W-1:0] rdata;
  reg [31:0] ref_mem [0:WORDS-1];
  integer i, b, p, errors = 0, seed;
  reg [31:0] exp;
  barg_ram #(.DEPTH_W(DEPTH_W), .DATA_W(DATA_W), .READ_PORTS(READ_PORTS)) dut (
    .clk(clk), .we(we), .be(be), .waddr(waddr), .wdata(wdata), .raddr(raddr), .rdata(rdata));
  always #5 clk = ~clk;
  task fail(input [8*72-1:0] why); begin $display("FAIL %0s", why); errors = errors + 1; end endtask
  initial begin
    seed = SEED;
    for (i = 0; i < WORDS; i = i + 1) ref_mem[i] = 0;
    for (i = 0; i < N; i = i + 1) begin
      @(negedge clk);
      for (p = 0; p < READ_PORTS; p = p + 1) begin
        exp = ref_mem[raddr[p*DEPTH_W +: DEPTH_W]];
        if (rdata[p*DATA_W +: DATA_W] !== exp) fail("read port");
      end
      we = $random(seed);
      be = $random(seed);
      waddr = $random(seed);
      wdata = $random(seed);
      if (($random(seed) & 3) == 0) begin be = 4'hF; we = 1; end
      for (p = 0; p < READ_PORTS; p = p + 1)
        raddr[p*DEPTH_W +: DEPTH_W] = ($random(seed) & 1) ? waddr : $random(seed);
      @(posedge clk);
      if (we) for (b = 0; b < 4; b = b + 1) if (be[b]) ref_mem[waddr][8*b +: 8] = wdata[8*b +: 8];
    end
    if (errors == 0) $display("PASS"); else $display("FAIL %0d errors", errors);
    $finish;
  end
endmodule
