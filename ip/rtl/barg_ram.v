// barg_ram: a synchronous-write, asynchronous-read RAM of 2^DEPTH_W words of DATA_W bits, with a byte enable per byte, and
// READ_PORTS read ports (raddr/rdata are packed: port k is bits k*DEPTH_W+:DEPTH_W and k*DATA_W+:DATA_W). Written by rule from its
// parameters (no model writes it). A read shows the contents before the edge (the write at that edge is not seen). The contents
// are all zero at power-up; reset does not clear them.
module barg_ram #(
  parameter integer DEPTH_W = 10,
  parameter integer DATA_W = 32,
  parameter integer READ_PORTS = 1
) (
  input  wire                             clk,
  input  wire                             we,
  input  wire [DATA_W/8-1:0]              be,
  input  wire [DEPTH_W-1:0]               waddr,
  input  wire [DATA_W-1:0]                wdata,
  input  wire [READ_PORTS*DEPTH_W-1:0]    raddr,
  output wire [READ_PORTS*DATA_W-1:0]     rdata
);
  localparam integer BYTES = DATA_W / 8;
  reg [DATA_W-1:0] mem [0:(1 << DEPTH_W) - 1];
  integer k, j;
  initial for (j = 0; j < (1 << DEPTH_W); j = j + 1) mem[j] = {DATA_W{1'b0}};
  always @(posedge clk) begin
    if (we) begin
      for (k = 0; k < BYTES; k = k + 1)
        if (be[k]) mem[waddr][8*k +: 8] <= wdata[8*k +: 8];
    end
  end
  genvar p;
  generate for (p = 0; p < READ_PORTS; p = p + 1) begin : rp
    assign rdata[p*DATA_W +: DATA_W] = mem[raddr[p*DEPTH_W +: DEPTH_W]];
  end endgenerate
endmodule
