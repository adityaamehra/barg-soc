module regfile3 (
  input  wire        clk,
  input  wire [6:0]  raddr,
  output wire [31:0] rdata,
  input  wire [6:0]  raddr2,
  output wire [31:0] rdata2,
  input  wire        we,
  input  wire [6:0]  waddr,
  input  wire [31:0] wdata
);

  reg [31:0] mem [0:127];

  // Synchronous write
  always @(posedge clk) begin
    if (we) begin
      mem[waddr] <= wdata;
    end
  end

  // Asynchronous reads
  assign rdata  = mem[raddr];
  assign rdata2 = mem[raddr2];

endmodule
