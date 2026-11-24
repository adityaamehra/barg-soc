// lsu: the load-store unit (demos/simt-gpu/README.md section 6, golden/lsu.py).
// HAND-WRITTEN from the golden model: the BARG-generated version (rtl/generated/lsu.v) lost the upper byte of a halfword load
// served in a later cycle of a bank-conflict sequence.
module lsu(
    input clk, rst, clear, valid,
    input [2:0] unit,
    input mem_store,
    input [2:0] mem_size,
    input [3:0] tmask,
    input [127:0] a, b,
    input [31:0] imm,
    input advance,
    input [127:0] g_rdata, s_rdata,
    output reg [3:0] g_en, g_we,
    output reg [35:0] g_addr,
    output reg [127:0] g_wdata,
    output reg [15:0] g_be,
    output reg [3:0] s_en, s_we,
    output reg [31:0] s_addr,
    output reg [127:0] s_wdata,
    output reg [15:0] s_be,
    output reg ready,
    output reg [127:0] y,
    output reg err
);

    reg        started;
    reg [3:0]  pend, got;
    reg [127:0] cap;

    wire act = valid & (unit == 3'd3);
    wire [2:0] nbytes = (mem_size == 3'd0 || mem_size == 3'd4) ? 3'd1 :
                        (mem_size == 3'd1 || mem_size == 3'd5) ? 3'd2 : 3'd4;
    wire signed_load = (mem_size == 3'd0 || mem_size == 3'd1);

    // per-lane decode
    reg [31:0] A [0:3];
    reg [3:0]  in_g, in_s, bad;
    reg [1:0]  bank [0:3];
    reg [1:0]  off [0:3];
    reg [8:0]  widx [0:3];
    integer k, j;
    always @* begin
        for (k = 0; k < 4; k = k + 1) begin
            A[k]    = a[32*k +: 32] + imm;
            in_g[k] = (A[k][31:13] == 19'h08000);          // 0x1000_0000 .. 0x1000_1FFF
            in_s[k] = (A[k][31:12] == 20'h20000);          // 0x2000_0000 .. 0x2000_0FFF
            bank[k] = A[k][3:2];
            off[k]  = A[k][1:0];
            widx[k] = in_g[k] ? A[k][12:4] : {1'b0, A[k][11:4]};
            bad[k]  = ~(in_g[k] | in_s[k]) | ((nbytes == 3'd2) & A[k][0]) | ((nbytes == 3'd4) & (A[k][1:0] != 2'b00));
        end
    end

    wire lsu_err = act & ~started & (|(tmask & bad));
    wire [3:0] P = started ? pend : tmask;

    // the lowest-numbered lane of P mapped to each (memory, bank) is chosen
    reg [3:0] chosen;
    always @* begin
        chosen = 4'b0000;
        for (k = 0; k < 4; k = k + 1) begin
            chosen[k] = P[k];
            for (j = 0; j < 4; j = j + 1)
                if (j < k && P[j] && (in_g[j] == in_g[k]) && (bank[j] == bank[k])) chosen[k] = 1'b0;
        end
        if (!act || lsu_err) chosen = 4'b0000;
    end

    // requests to the banks
    reg [3:0] be_lane;
    always @* begin
        g_en = 4'b0; g_we = 4'b0; g_addr = 36'd0; g_wdata = 128'd0; g_be = 16'd0;
        s_en = 4'b0; s_we = 4'b0; s_addr = 32'd0; s_wdata = 128'd0; s_be = 16'd0;
        for (k = 0; k < 4; k = k + 1) begin
            be_lane = ((4'b0001 << nbytes) - 4'b0001) << off[k];
            if (chosen[k] && in_g[k]) begin
                g_en[bank[k]] = 1'b1;
                g_we[bank[k]] = mem_store;
                g_addr[9*bank[k] +: 9] = widx[k];
                g_wdata[32*bank[k] +: 32] = b[32*k +: 32] << (8 * off[k]);
                g_be[4*bank[k] +: 4] = be_lane;
            end
            if (chosen[k] && in_s[k]) begin
                s_en[bank[k]] = 1'b1;
                s_we[bank[k]] = mem_store;
                s_addr[8*bank[k] +: 8] = widx[k][7:0];
                s_wdata[32*bank[k] +: 32] = b[32*k +: 32] << (8 * off[k]);
                s_be[4*bank[k] +: 4] = be_lane;
            end
        end
    end

    // loaded data: the lanes whose word arrives this cycle replace their lane of cap
    reg [127:0] cur;
    reg [31:0] word, shifted, ext;
    always @* begin
        cur = cap;
        for (k = 0; k < 4; k = k + 1) begin
            word = in_g[k] ? g_rdata[32*bank[k] +: 32] : s_rdata[32*bank[k] +: 32];
            shifted = word >> (8 * off[k]);
            case (nbytes)
                3'd1:    ext = signed_load ? {{24{shifted[7]}},  shifted[7:0]}  : {24'd0, shifted[7:0]};
                3'd2:    ext = signed_load ? {{16{shifted[15]}}, shifted[15:0]} : {16'd0, shifted[15:0]};
                default: ext = shifted;
            endcase
            if (got[k]) cur[32*k +: 32] = ext;
        end
    end

    always @* begin
        err   = act ? lsu_err : 1'b0;
        y     = act ? cur : cap;
        ready = act & (lsu_err | (mem_store & ((P & ~chosen) == 4'b0000)) | (~mem_store & started & (P == 4'b0000)));
    end

    always @(posedge clk) begin
        if (rst) begin
            started <= 1'b0; pend <= 4'b0; got <= 4'b0; cap <= 128'd0;
        end else if (clear | advance) begin
            started <= 1'b0; pend <= 4'b0; got <= 4'b0;
        end else if (act & ~lsu_err) begin
            started <= 1'b1;
            pend    <= P & ~chosen;
            got     <= mem_store ? 4'b0000 : chosen;
            cap     <= cur;
        end
    end

endmodule
