module dx_reg (
    input wire clk,
    input wire rst,
    input wire clear,
    input wire hold,
    input wire valid_in,
    input wire [1:0] wid_in,
    input wire [31:0] pc_in,
    input wire [3:0] tmask_in,
    input wire [4:0] rd_in,
    input wire [2:0] unit_in,
    input wire [3:0] alu_op_in,
    input wire a_sel_in,
    input wire b_sel_in,
    input wire [2:0] wb_src_in,
    input wire regwrite_in,
    input wire [1:0] ctrl_in,
    input wire [2:0] br_op_in,
    input wire mem_store_in,
    input wire [2:0] mem_size_in,
    input wire [1:0] md_op_in,
    input wire [2:0] simt_op_in,
    input wire [1:0] simt_mode_in,
    input wire [1:0] tensor_op_in,
    input wire [11:0] csr_addr_in,
    input wire illegal_in,
    input wire [31:0] imm_in,
    input wire [127:0] a_in,
    input wire [127:0] b_in,
    output reg valid_out,
    output reg [1:0] wid_out,
    output reg [31:0] pc_out,
    output reg [3:0] tmask_out,
    output reg [4:0] rd_out,
    output reg [2:0] unit_out,
    output reg [3:0] alu_op_out,
    output reg a_sel_out,
    output reg b_sel_out,
    output reg [2:0] wb_src_out,
    output reg regwrite_out,
    output reg [1:0] ctrl_out,
    output reg [2:0] br_op_out,
    output reg mem_store_out,
    output reg [2:0] mem_size_out,
    output reg [1:0] md_op_out,
    output reg [2:0] simt_op_out,
    output reg [1:0] simt_mode_out,
    output reg [1:0] tensor_op_out,
    output reg [11:0] csr_addr_out,
    output reg illegal_out,
    output reg [31:0] imm_out,
    output reg [127:0] a_out,
    output reg [127:0] b_out
);

    always @(posedge clk) begin
        if (rst | clear) begin
            valid_out      <= 1'b0;
            wid_out        <= 2'd0;
            pc_out         <= 32'd0;
            tmask_out      <= 4'd0;
            rd_out         <= 5'd0;
            unit_out       <= 3'd0;
            alu_op_out     <= 4'd0;
            a_sel_out      <= 1'b0;
            b_sel_out      <= 1'b0;
            wb_src_out     <= 3'd0;
            regwrite_out   <= 1'b0;
            ctrl_out       <= 2'd0;
            br_op_out      <= 3'd0;
            mem_store_out  <= 1'b0;
            mem_size_out   <= 3'd0;
            md_op_out      <= 2'd0;
            simt_op_out    <= 3'd0;
            simt_mode_out  <= 2'd0;
            tensor_op_out  <= 2'd0;
            csr_addr_out   <= 12'd0;
            illegal_out    <= 1'b0;
            imm_out        <= 32'd0;
            a_out          <= 128'd0;
            b_out          <= 128'd0;
        end else if (hold) begin
            // keep all values
        end else begin
            valid_out      <= valid_in;
            wid_out        <= wid_in;
            pc_out         <= pc_in;
            tmask_out      <= tmask_in;
            rd_out         <= rd_in;
            unit_out       <= unit_in;
            alu_op_out     <= alu_op_in;
            a_sel_out      <= a_sel_in;
            b_sel_out      <= b_sel_in;
            wb_src_out     <= wb_src_in;
            regwrite_out   <= regwrite_in;
            ctrl_out       <= ctrl_in;
            br_op_out      <= br_op_in;
            mem_store_out  <= mem_store_in;
            mem_size_out   <= mem_size_in;
            md_op_out      <= md_op_in;
            simt_op_out    <= simt_op_in;
            simt_mode_out  <= simt_mode_in;
            tensor_op_out  <= tensor_op_in;
            csr_addr_out   <= csr_addr_in;
            illegal_out    <= illegal_in;
            imm_out        <= imm_in;
            a_out          <= a_in;
            b_out          <= b_in;
        end
    end

endmodule
