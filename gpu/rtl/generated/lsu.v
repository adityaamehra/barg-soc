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
    wire act = valid & (unit == 3'b011);

    reg started;
    reg [3:0] pend, got;
    reg [127:0] cap;

    reg [3:0] Pv, chosen, bad;
    reg [127:0] cur;
    integer i, j, k;
    reg [31:0] laddr [0:3];
    reg [1:0] lbank [0:3];
    reg [1:0] loff [0:3];
    reg [2:0] ln [0:3];
    reg ling [0:3], lins [0:3];
    reg [31:0] word, ext;
    reg [7:0] bytev, halfv, bemask;
    reg found;

    always @* begin
        g_en = 4'd0; g_we = 4'd0; g_addr = 36'd0; g_wdata = 128'd0; g_be = 16'd0;
        s_en = 4'd0; s_we = 4'd0; s_addr = 32'd0; s_wdata = 128'd0; s_be = 16'd0;
        ready = 1'b0; err = 1'b0;
        cur = cap;
        y = cap;
        chosen = 4'd0;
        bad = 4'd0;
        Pv = started ? pend : tmask;

        for (i = 0; i < 4; i = i + 1) begin
            laddr[i] = a[32*i +: 32] + imm;
            ling[i] = (laddr[i] >= 32'h1000_0000) && (laddr[i] < 32'h1000_2000);
            lins[i] = (laddr[i] >= 32'h2000_0000) && (laddr[i] < 32'h2000_1000);
            lbank[i] = laddr[i][3:2];
            loff[i] = laddr[i][1:0];
            if (mem_size == 3'd0 || mem_size == 3'd4)
                ln[i] = 3'd1;
            else if (mem_size == 3'd1 || mem_size == 3'd5)
                ln[i] = 3'd2;
            else
                ln[i] = 3'd4;
            if (tmask[i] && (((laddr[i] & (ln[i] - 1)) != 32'd0) || !(ling[i] || lins[i])))
                bad[i] = 1'b1;
        end
        err = act & !started & (bad != 4'd0);

        for (i = 0; i < 4; i = i + 1) begin
            chosen[i] = Pv[i];
            for (j = 0; j < i; j = j + 1) begin
                if (Pv[j] && (ling[j] == ling[i]) && (lins[j] == lins[i]) && (lbank[j] == lbank[i]))
                    chosen[i] = 1'b0;
            end
        end

        if (act && !err) begin
            for (k = 0; k < 4; k = k + 1) begin
                found = 1'b0;
                for (i = 0; i < 4; i = i + 1) begin
                    if (!found && chosen[i] && ling[i] && (lbank[i] == k[1:0])) begin
                        found = 1'b1;
                        g_en[k] = 1'b1;
                        g_we[k] = mem_store;
                        g_addr[9*k +: 9] = laddr[i][12:4];
                        g_wdata[32*k +: 32] = b[32*i +: 32] << (8*loff[i]);
                        case (ln[i])
                            3'd1: bemask = 8'h01;
                            3'd2: bemask = 8'h03;
                            default: bemask = 8'h0F;
                        endcase
                        g_be[4*k +: 4] = bemask << loff[i];
                    end
                end
                found = 1'b0;
                for (i = 0; i < 4; i = i + 1) begin
                    if (!found && chosen[i] && lins[i] && (lbank[i] == k[1:0])) begin
                        found = 1'b1;
                        s_en[k] = 1'b1;
                        s_we[k] = mem_store;
                        s_addr[8*k +: 8] = laddr[i][11:4];
                        s_wdata[32*k +: 32] = b[32*i +: 32] << (8*loff[i]);
                        case (ln[i])
                            3'd1: bemask = 8'h01;
                            3'd2: bemask = 8'h03;
                            default: bemask = 8'h0F;
                        endcase
                        s_be[4*k +: 4] = bemask << loff[i];
                    end
                end
            end
        end

        for (i = 0; i < 4; i = i + 1) begin
            if (got[i]) begin
                if (ling[i])
                    word = g_rdata[32*lbank[i] +: 32];
                else
                    word = s_rdata[32*lbank[i] +: 32];
                if (ln[i] == 3'd1) begin
                    bytev = word[8*loff[i] +: 8];
                    ext = (mem_size == 3'd0) ? {{24{bytev[7]}}, bytev} : {24'd0, bytev};
                end else if (ln[i] == 3'd2) begin
                    halfv = loff[i][1] ? word[31:16] : word[15:0];
                    ext = (mem_size == 3'd1) ? {{16{halfv[7]}}, halfv} : {16'd0, halfv};
                end else begin
                    ext = word;
                end
                cur[32*i +: 32] = ext;
            end
        end
        y = cur;

        ready = act & (err
                     | (mem_store & ((Pv & ~chosen) == 4'd0))
                     | (!mem_store & started & (Pv == 4'd0)));
    end

    always @(posedge clk) begin
        if (rst) begin
            started <= 1'b0;
            pend <= 4'd0;
            got <= 4'd0;
            cap <= 128'd0;
        end else if (clear || advance) begin
            started <= 1'b0;
            pend <= 4'd0;
            got <= 4'd0;
        end else if (act && !err) begin
            started <= 1'b1;
            pend <= Pv & ~chosen;
            got <= mem_store ? 4'd0 : chosen;
            cap <= cur;
        end
    end

endmodule
