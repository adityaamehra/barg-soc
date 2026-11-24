module bp_resolve (
    input  wire [1:0]   pcsel,
    input  wire         br_redirect,
    input  wire [31:0]  br_pc,
    input  wire         valid,
    input  wire [31:0]  pc_plus4,
    input  wire         pt,
    input  wire [31:0]  ptarget,
    input  wire [7:0]   pidx,
    output wire         redirect,
    output wire [31:0]  redirect_pc,
    output wire         upd_en,
    output wire [7:0]   upd_idx,
    output wire         upd_taken,
    output wire         upd_cond,
    output wire         upd_jump
);

    wire actual = valid & br_redirect;
    wire mispredict = valid & ( (pt ^ actual) | (actual & (ptarget != br_pc)) );

    assign redirect     = mispredict;
    assign redirect_pc  = actual ? br_pc : pc_plus4;
    assign upd_en       = valid & (pcsel != 2'b00);
    assign upd_idx      = pidx;
    assign upd_taken    = actual;
    assign upd_cond     = (pcsel == 2'b01);
    assign upd_jump     = (pcsel == 2'b10) | (pcsel == 2'b11);

endmodule
