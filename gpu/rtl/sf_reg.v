module sf_reg (
    input  wire        clk,
    input  wire        rst,
    input  wire        clear,
    input  wire        hold,
    input  wire        valid_in,
    input  wire [1:0]  wid_in,
    input  wire [31:0] pc_in,
    input  wire [3:0]  tmask_in,
    output reg         valid_out,
    output reg  [1:0]  wid_out,
    output reg  [31:0] pc_out,
    output reg  [3:0]  tmask_out
);

always @(posedge clk) begin
    if (rst || clear) begin
        valid_out <= 1'b0;
        wid_out   <= 2'b00;
        pc_out    <= 32'h00000000;
        tmask_out <= 4'b0000;
    end else if (hold) begin
        valid_out <= valid_out;
        wid_out   <= wid_out;
        pc_out    <= pc_out;
        tmask_out <= tmask_out;
    end else begin
        valid_out <= valid_in;
        wid_out   <= wid_in;
        pc_out    <= pc_in;
        tmask_out <= tmask_in;
    end
end

endmodule
