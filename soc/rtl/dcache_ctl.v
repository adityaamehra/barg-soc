module dcache_ctl (
    input  wire        clk,
    input  wire        rst,
    input  wire        req,
    input  wire        is_ram,
    input  wire        is_store,
    input  wire        is_amo,
    input  wire        hit,
    input  wire        hold,
    input  wire [31:0] addr,
    input  wire        done,
    input  wire [255:0] line,
    input  wire        wdone,
    input  wire [31:0] waddr,
    input  wire        self,
    input  wire        w_plain,
    output wire        serve,
    output wire        dmiss,
    output wire        rq,
    output wire [31:0] rq_addr,
    output wire        fill_en,
    output wire [31:0] fill_addr,
    output wire [255:0] fill_data,
    output wire        wr_en,
    output wire [31:0] wr_addr,
    output wire        inv_en,
    output wire [31:0] inv_addr
);

    reg [31:0] ra;
    reg        busy;

    wire is_load = req & is_ram & ~is_store & ~is_amo & ~hold;

    assign serve     = is_load & hit;
    assign dmiss     = is_load & ~hit;
    assign rq        = busy;
    assign rq_addr   = ra;
    assign fill_en   = busy & done;
    assign fill_addr = ra;
    assign fill_data = line;
    assign wr_en     = wdone & self & w_plain;
    assign wr_addr   = waddr;
    assign inv_en    = wdone & ~(self & w_plain);
    assign inv_addr  = waddr;

    always @(posedge clk) begin
        if (rst) begin
            ra   <= 32'b0;
            busy <= 1'b0;
        end else begin
            if (!busy && dmiss) begin
                ra   <= addr & ~32'h1F; // clear bits 4:0
                busy <= 1'b1;
            end else if (busy && done) begin
                busy <= 1'b0;
            end
        end
    end

endmodule
