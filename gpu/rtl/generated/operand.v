module operand (
  input  [1:0]   wid,
  input  [4:0]   rs1,
  input  [4:0]   rs2,
  input  [31:0]  rdata1_0,
  input  [31:0]  rdata1_1,
  input  [31:0]  rdata1_2,
  input  [31:0]  rdata1_3,
  input  [31:0]  rdata2_0,
  input  [31:0]  rdata2_1,
  input  [31:0]  rdata2_2,
  input  [31:0]  rdata2_3,
  output [6:0]   raddr1,
  output [6:0]   raddr2,
  output [127:0] a,
  output [127:0] b
);

  assign raddr1 = {wid, rs1};
  assign raddr2 = {wid, rs2};

  wire [127:0] a_gather;
  wire [127:0] b_gather;

  assign a_gather = {rdata1_3, rdata1_2, rdata1_1, rdata1_0};
  assign b_gather = {rdata2_3, rdata2_2, rdata2_1, rdata2_0};

  assign a = (rs1 == 5'd0) ? 128'd0 : a_gather;
  assign b = (rs2 == 5'd0) ? 128'd0 : b_gather;

endmodule
