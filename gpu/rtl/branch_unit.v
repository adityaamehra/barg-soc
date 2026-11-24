module branch_unit (
    input  wire [1:0]  ctrl,
    input  wire [3:0]  taken,
    input  wire [3:0]  tmask,
    input  wire [31:0] pc,
    input  wire [31:0] imm,
    input  wire [127:0] a,
    output wire [31:0] next_pc,
    output wire [31:0] link,
    output wire        diverged
);
    // lowest-numbered active lane
    wire [1:0] l = tmask[0] ? 2'd0 :
                   tmask[1] ? 2'd1 :
                   tmask[2] ? 2'd2 : 2'd3;
     wire taken_l = taken[l];
     wire [31:0] jalr_pc = (a[l*32 +: 32] + imm) & 32'hFFFFFFFE;
    wire [31:0] jalr_pc0 = (a[0*32 +: 32] + imm) & 32'hFFFFFFFE;
    wire [31:0] jalr_pc1 = (a[1*32 +: 32] + imm) & 32'hFFFFFFFE;
    wire [31:0] jalr_pc2 = (a[2*32 +: 32] + imm) & 32'hFFFFFFFE;
    wire [31:0] jalr_pc3 = (a[3*32 +: 32] + imm) & 32'hFFFFFFFE;
  
    assign link = pc + 32'd4;
 
    reg [31:0] npc;
    always @* begin
        case (ctrl)
            2'b00: npc = pc + 32'd4;                       // NONE
            2'b01: npc = taken_l ? (pc + imm) : (pc + 32'd4); // BRANCH
            2'b10: npc = pc + imm;                         // JAL
            2'b11: npc = jalr_pc;                          // JALR
            default: npc = pc + 32'd4;
        endcase
    end
 
    assign next_pc = (tmask == 4'b0000) ? (pc + 32'd4) : npc;

    // diverged: two active lanes would choose different next pcs (branch taken bits differ)
    reg div;
    always @* begin
         div = 1'b0;
         if (ctrl == 2'b01 && tmask != 4'b0000) begin
            if (tmask[0] && tmask[1] && (taken[0] != taken[1])) div = 1'b1;
            if (tmask[0] && tmask[2] && (taken[0] != taken[2])) div = 1'b1;
            if (tmask[0] && tmask[3] && (taken[0] != taken[3])) div = 1'b1;
            if (tmask[1] && tmask[2] && (taken[1] != taken[2])) div = 1'b1;
            if (tmask[1] && tmask[3] && (taken[1] != taken[3])) div = 1'b1;
            if (tmask[2] && tmask[3] && (taken[2] != taken[3])) div = 1'b1;
        end
        if (ctrl == 2'b11 && tmask != 4'b0000) begin
            if (tmask[0] && tmask[1] && (jalr_pc0 != jalr_pc1)) div = 1'b1;
            if (tmask[0] && tmask[2] && (jalr_pc0 != jalr_pc2)) div = 1'b1;
            if (tmask[0] && tmask[3] && (jalr_pc0 != jalr_pc3)) div = 1'b1;
            if (tmask[1] && tmask[2] && (jalr_pc1 != jalr_pc2)) div = 1'b1;
            if (tmask[1] && tmask[3] && (jalr_pc1 != jalr_pc3)) div = 1'b1;
            if (tmask[2] && tmask[3] && (jalr_pc2 != jalr_pc3)) div = 1'b1;
        end
    end

    assign diverged = div;
endmodule
