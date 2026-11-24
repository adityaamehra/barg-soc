module trap_unit (
    input  wire        valid,
    input  wire        xcpt,
    input  wire        irq,
    input  wire [3:0]  cause,
    input  wire [31:0] pc,
    input  wire [31:0] tval,
    input  wire [31:0] inst,
    input  wire [2:0]  csrop,
    input  wire        is_mret,
    input  wire        illegal_csr,
    input  wire [1:0]  priv,
    input  wire        tsr,
    input  wire        tvm,
    input  wire [15:0] medeleg,
    input  wire [11:0] mideleg,
    input  wire [31:0] mtvec,
    input  wire [31:0] stvec,
    input  wire [31:0] mepc,
    input  wire [31:0] sepc,
    output wire        redirect,
    output wire        kill,
    output wire [31:0] redirect_pc,
    output wire        trap_m,
    output wire        trap_s,
    output wire        mret,
    output wire        sret,
    output wire        csr_we,
    output wire        sfence,
    output wire        retire,
    output wire [31:0] epc,
    output wire [31:0] cause_val,
    output wire [31:0] tval_out
);

    reg        illegal;
    reg        trap;
    reg [3:0]  c;
    reg        is_int;
    reg [31:0] t;
    reg        deleg;
    reg        trap_s_r, trap_m_r;
    reg        mret_r, sret_r;
    reg        csr_we_r, sfence_r;
    reg        refetch;
    reg        redirect_r, kill_r;
    reg        retire_r;
    reg [31:0] epc_r;
    reg [31:0] cause_val_r;
    reg [31:0] tval_out_r;
    reg [31:0] redirect_pc_r;

    // Vector function
    function [31:0] vector;
        input [31:0] v;
        input        is_int;
        input [3:0]  c;
        begin
            vector = (v & 32'hFFFFFFFC) + ((is_int && v[0]) ? (c * 4) : 32'd0);
        end
    endfunction

    always @* begin
        // illegal
        illegal = illegal_csr |
                  (is_mret && (priv != 2'b11)) |
                  ((csrop == 3'b101) && (priv == 2'b00 || (priv == 2'b01 && tsr))) |
                  ((csrop == 3'b110) && (priv == 2'b00 || (priv == 2'b01 && tvm)));

        // trap
        trap = valid && (xcpt || illegal);

        // c
        c = xcpt ? cause : 4'd2;

        // is_int
        is_int = xcpt && irq;

        // t
        if (is_int)
            t = 32'd0;
        else if (xcpt)
            t = tval;
        else
            t = inst;

        // deleg
        if (priv != 2'b11) begin
            if (is_int)
                deleg = mideleg[c]; // c up to 11, mideleg 12 bits
            else
                deleg = medeleg[c]; // c up to 15, medeleg 16 bits
        end else begin
            deleg = 1'b0;
        end

        // trap_s, trap_m
        trap_s_r = trap && deleg;
        trap_m_r = trap && !deleg;

        // mret, sret
        mret_r = valid && !trap && is_mret;
        sret_r = valid && !trap && (csrop == 3'b101);

        // csr_we
        csr_we_r = valid && !trap && (csrop == 3'b010 || csrop == 3'b011 || csrop == 3'b100);

        // sfence
        sfence_r = valid && !trap && (csrop == 3'b110);

        // refetch
        refetch = valid && !trap && (csrop == 3'b010 || csrop == 3'b011 || csrop == 3'b100 || csrop == 3'b110 || csrop == 3'b111);

        // redirect
        redirect_r = trap || mret_r || sret_r || refetch;

        // kill
        kill_r = trap || mret_r || sret_r;

        // retire
        retire_r = valid && !trap;

        // epc
        epc_r = pc & 32'hFFFFFFFE;

        // cause_val
        cause_val_r = {is_int, 27'd0, c};

        // tval_out
        tval_out_r = t;

        // redirect_pc
        if (trap_m_r)
            redirect_pc_r = vector(mtvec, is_int, c);
        else if (trap_s_r)
            redirect_pc_r = vector(stvec, is_int, c);
        else if (mret_r)
            redirect_pc_r = mepc;
        else if (sret_r)
            redirect_pc_r = sepc;
        else
            redirect_pc_r = pc + 32'd4;
    end

    assign redirect    = redirect_r;
    assign kill        = kill_r;
    assign redirect_pc = redirect_pc_r;
    assign trap_m      = trap_m_r;
    assign trap_s      = trap_s_r;
    assign mret        = mret_r;
    assign sret        = sret_r;
    assign csr_we      = csr_we_r;
    assign sfence      = sfence_r;
    assign retire      = retire_r;
    assign epc         = epc_r;
    assign cause_val   = cause_val_r;
    assign tval_out    = tval_out_r;

endmodule
