module fp_wb (
    input  wire [31:0] inst,
    input  wire        commit,
    input  wire [1:0]  dwsel,
    input  wire [31:0] mem_rdata,
    input  wire [63:0] fres,
    input  wire [4:0]  flags,
    input  wire        wrf,
    output wire        we_lo,
    output wire        we_hi,
    output wire [4:0]  waddr,
    output wire [31:0] wdata_lo,
    output wire [31:0] wdata_hi,
    output wire [4:0]  flags_set,
    output wire        dirty_set
);

    wire [6:0] opcode = inst[6:0];
    wire       is_load = commit && (opcode == 7'b0000111);
    wire       is_op   = commit && (
                            (opcode == 7'b1000011) ||
                            (opcode == 7'b1000111) ||
                            (opcode == 7'b1001011) ||
                            (opcode == 7'b1001111) ||
                            (opcode == 7'b1010011)
                         );
    assign waddr = inst[11:7];

    assign we_lo = (is_load && (dwsel != 2'b10)) || (is_op && wrf);
    assign we_hi = (is_load && (dwsel != 2'b01)) || (is_op && wrf);

    assign wdata_lo = is_load ? mem_rdata : fres[31:0];
    assign wdata_hi = is_load ? (dwsel == 2'b10 ? mem_rdata : 32'hFFFFFFFF) : fres[63:32];

    assign flags_set = is_op ? flags : 5'b0;
    assign dirty_set = is_load || (is_op && (wrf || (flags != 5'b0)));

endmodule
