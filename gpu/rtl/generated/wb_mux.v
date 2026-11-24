module wb_mux (
    input  wire        advance,
    input  wire        regwrite,
    input  wire [4:0]  rd,
    input  wire [1:0]  wid,
    input  wire [3:0]  tmask,
    input  wire [2:0]  wb_src,
    input  wire [127:0] alu_y,
    input  wire [127:0] mul_y,
    input  wire [127:0] div_y,
    input  wire [127:0] load_y,
    input  wire [127:0] simt_y,
    input  wire [127:0] tensor_y,
    input  wire [127:0] csr_y,
    input  wire [31:0]  link,
    output wire        we0,
    output wire        we1,
    output wire        we2,
    output wire        we3,
    output wire [6:0]  waddr,
    output wire [31:0] wdata0,
    output wire [31:0] wdata1,
    output wire [31:0] wdata2,
    output wire [31:0] wdata3
);
     wire w = advance & regwrite & (rd != 5'd0);

    reg [127:0] r;
    always @* begin
        case (wb_src)
            3'b000: r = alu_y;
            3'b001: r = mul_y;
            3'b010: r = div_y;
            3'b011: r = load_y;
            3'b100: r = simt_y;
            3'b101: r = tensor_y;
            3'b110: r = csr_y;
            3'b111: r = {link, link, link, link};
            default: r = {32'd0, 32'd0, 32'd0, 32'd0};
        endcase
    end

    assign we0 = w & tmask[0];
    assign we1 = w & tmask[1];
    assign we2 = w & tmask[2];
    assign we3 = w & tmask[3];

     assign waddr  = {wid, rd};

    assign wdata0 = r[31:0];
    assign wdata1 = r[63:32];
    assign wdata2 = r[95:64];
    assign wdata3 = r[127:96];
endmodule
