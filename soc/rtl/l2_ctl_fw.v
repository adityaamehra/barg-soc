module l2_ctl_fw (
    input clk,
    input rst,
    input rv,
    input rwe,
    input rline,
    input [31:0] raddr,
    input [31:0] rwdata,
    input [3:0] rwstrb,
    input pair,
    input hit_a,
    input hit_b,
    input [255:0] line_a,
    input [255:0] line_b,
    input d_ready,
    input d_valid,
    input [255:0] d_data,
    output ready,
    output resp_valid,
    output [255:0] resp_data,
    output [31:0] lk_addr,
    output dv,
    output dwe,
    output dline,
    output [31:0] daddr,
    output [31:0] dwdata,
    output [3:0] dwstrb,
    output fill_a_en,
    output fill_b_en,
    output [31:0] fill_addr,
    output [255:0] fill_data,
    output inv_en,
    output [31:0] inv_addr
);
    localparam [2:0] IDLE  = 3'd0;
    localparam [2:0] LOOK  = 3'd1;
    localparam [2:0] DREQ  = 3'd2;
    localparam [2:0] DWAIT = 3'd3;
    localparam [2:0] FILL  = 3'd4;
    localparam [2:0] RESP  = 3'd5;

    reg [2:0] state;
    reg we_q;
    reg line_q;
    reg pair_q;
    reg f_q;
    reg [31:0] addr_q;
    reg [31:0] wd_q;
    reg [3:0] ws_q;
    reg [255:0] data_q;

    wire sel_hit;

    assign sel_hit = pair_q ? hit_b : hit_a;

    always @(posedge clk) begin
        if (rst) begin
            state  <= IDLE;
            we_q   <= 1'b0;
            line_q <= 1'b0;
            pair_q <= 1'b0;
            f_q    <= 1'b0;
            addr_q <= 32'd0;
            wd_q   <= 32'd0;
            ws_q   <= 4'd0;
            data_q <= 256'd0;
        end else begin
            case (state)
        IDLE: begin
            if (rv) begin
                we_q   <= rwe;
                line_q <= rline;
                addr_q <= raddr;
                wd_q   <= rwdata;
                ws_q   <= rwstrb;
                pair_q <= pair;
                state  <= (rwe ? DREQ : LOOK);
            end
        end
                LOOK: begin
                    if (!we_q && line_q && sel_hit) begin
                        f_q   <= 1'b1;
                        state <= RESP;
                    end else begin
                        f_q   <= 1'b0;
                        state <= DREQ;
                    end
                end
                DREQ: begin
                    if (d_ready) begin
                        state <= DWAIT;
                    end
                end
        DWAIT: begin
            if (d_valid) begin
                data_q <= d_data;
                if (we_q)
                    state <= IDLE;
                else if (!line_q)
                    state <= RESP;
                else
                    state <= FILL;
            end
        end
                FILL: begin
                    state <= RESP;
                end
                RESP: begin
                    state <= IDLE;
                end
        default: begin
            if (rv) begin
                we_q   <= rwe;
                line_q <= rline;
                addr_q <= raddr;
                wd_q   <= rwdata;
                ws_q   <= rwstrb;
                pair_q <= pair;
                state  <= (rwe ? DREQ : LOOK);
            end
        end
            endcase
        end
    end

    assign ready = (state == IDLE) || (state == 3'd6) || (state == 3'd7);
    assign resp_valid = (state == RESP) || (state == DWAIT && d_valid && we_q);
    assign resp_data = (state == RESP)
        ? (we_q ? 256'd0 : (f_q ? (pair_q ? line_b : line_a) : data_q))
        : 256'd0;

    assign lk_addr = addr_q;

    assign dv = (state == DREQ);
    assign dwe = we_q;
    assign dline = line_q;
    assign daddr = addr_q;
    assign dwdata = wd_q;
    assign dwstrb = ws_q;

    assign fill_a_en = (state == FILL) && !pair_q;
    assign fill_b_en = (state == FILL) && pair_q;
    assign fill_addr = addr_q;
    assign fill_data = data_q;

    assign inv_en = (state == IDLE && rv && rwe);
    assign inv_addr = (state == IDLE) ? raddr : addr_q;
endmodule
