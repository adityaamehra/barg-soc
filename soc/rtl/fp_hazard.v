module fp_hazard (
    input  wire        stall,
    input  wire        flush_id_ex,
    input  wire        md_stall,
    input  wire        dw_hold,
    input  wire        id_valid,
    input  wire        id_is_fp,
    input  wire        half2,
    input  wire        ex_valid,
    input  wire [31:0] ex_inst,
    input  wire        mem_valid,
    input  wire [31:0] mem_inst,
    output wire        stall_out,
    output wire        flush_out
);

    // Writer opcodes: 0000111, 1000011, 1000111, 1001011, 1001111, 1010011
    function is_writer;
        input [6:0] opcode;
        begin
            case (opcode)
                7'b0000111,
                7'b1000011,
                7'b1000111,
                7'b1001011,
                7'b1001111,
                7'b1010011: is_writer = 1'b1;
                default:    is_writer = 1'b0;
            endcase
        end
    endfunction

    wire ex_wr  = ex_valid  & is_writer(ex_inst[6:0]);
    wire mem_wr = mem_valid & is_writer(mem_inst[6:0]);

    wire wait_sig = id_valid & id_is_fp & ~half2 & (ex_wr | mem_wr);

    assign stall_out  = stall  | dw_hold | wait_sig;
    assign flush_out  = flush_id_ex | (wait_sig & ~md_stall);

endmodule
