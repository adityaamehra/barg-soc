module ifetch_ctl (
    input  wire         clk,
    input  wire         rst,
    input  wire         hit_lo,
    input  wire         hit_hi,
    input  wire         need_hi,
    input  wire         hold,
    input  wire [31:0]  lo_addr,
    input  wire [31:0]  hi_addr,
    input  wire         done,
    input  wire [255:0] line,
    input  wire         fence,
    input  wire         adv,
    output wire         imiss,
    output wire         rq,
    output wire [31:0]  rq_addr,
    output wire         fill_en,
    output wire [31:0]  fill_addr,
    output wire [255:0] fill_data,
    output wire         inv_all
);

    reg  [31:0] ra;
    reg         busy;

    wire miss_lo = ~hit_lo;
    wire miss_hi = need_hi & ~hit_hi;
    wire imiss_int = (miss_lo | miss_hi) & ~hold;

    assign imiss     = imiss_int;
    assign rq        = busy;
    assign fill_en   = busy & done;
    assign rq_addr   = ra;
    assign fill_addr = ra;
    assign fill_data = line;
    assign inv_all   = fence & adv;

    always @(posedge clk) begin
        if (rst) begin
            ra   <= 32'd0;
            busy <= 1'b0;
        end else begin
            if (!busy && imiss_int) begin
                ra   <= miss_lo ? (lo_addr & 32'hFFFFFFE0) : (hi_addr & 32'hFFFFFFE0);
                busy <= 1'b1;
            end else if (busy && done) begin
                busy <= 1'b0;
            end
        end
    end

endmodule
