// Synchronous FIFO, 2**AW entries of W bits, valid/ready on both sides. Synchronous active-high reset.
// out_data is valid whenever out_valid is high (first-word fall-through).
module barg_fifo #(
  parameter integer W  = 8,
  parameter integer AW = 2
) (
  input  wire         clk,
  input  wire         rst,
  input  wire [W-1:0] in_data,
  input  wire         in_valid,
  output wire         in_ready,
  output wire [W-1:0] out_data,
  output wire         out_valid,
  input  wire         out_ready
);
  reg [W-1:0] mem [0:(1<<AW)-1];
  reg [AW:0]  wp, rp;
  wire empty = (wp == rp);
  wire full  = (wp[AW] != rp[AW]) && (wp[AW-1:0] == rp[AW-1:0]);
  assign in_ready  = !full;
  assign out_valid = !empty;
  assign out_data  = mem[rp[AW-1:0]];
  always @(posedge clk) begin
    if (rst) begin
      wp <= 0;
      rp <= 0;
    end else begin
      if (in_valid && !full) begin
        mem[wp[AW-1:0]] <= in_data;
        wp <= wp + 1'b1;
      end
      if (!empty && out_ready) rp <= rp + 1'b1;
    end
  end
endmodule
