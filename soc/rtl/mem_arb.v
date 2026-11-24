module mem_arb (
    input  wire        clk,
    input  wire        rst,
    input  wire        req0,
    input  wire        req1,
    input  wire        req2,
    input  wire        req3,
    input  wire [1:0]  kind0,
    input  wire [1:0]  kind1,
    input  wire [1:0]  kind2,
    input  wire [1:0]  kind3,
    input  wire        is_ram,
    input  wire        c_store,
    input  wire        c_amo,
    input  wire        c_dmem_we,
    input  wire        eng_ready,
    input  wire        eng_done,
    output reg         sel0,
    output reg         sel1,
    output reg         sel2,
    output reg         sel3,
    output reg         bsel0,
    output reg         bsel1,
    output reg         bsel2,
    output reg         bsel3,
    output reg         grant0,
    output reg         grant1,
    output reg         grant2,
    output reg         grant3,
    output reg         eng_start,
    output reg         eng_we,
    output reg         eng_line,
    output reg [1:0]   eng_src,
    output reg         rdone,
    output reg         wdone
);

    localparam S_IDLE                 = 3'd0,
               S_READ_WAIT            = 3'd1,
               S_WRITE_WAIT           = 3'd2,
               S_ATOMIC_READ_WAIT     = 3'd3,
               S_ATOMIC_DECIDE        = 3'd4,
               S_ATOMIC_WRITE_WAIT    = 3'd5;

    reg [2:0] state;
    reg [1:0] cur;
    reg       core;
    reg [1:0] last;

    reg [2:0] next_state;
    reg [1:0] next_cur;
    reg       next_core;
    reg [1:0] next_last;

    reg [3:0] eligible;
    reg       w_exists;
    reg [1:0] w;
    reg [1:0] kw;
    reg       cstore, camo, cload, dev, start;

    always @* begin
        eligible[0] = req0 && (kind0 != 2'b11);
        eligible[1] = req1 && (kind1 != 2'b11);
        eligible[2] = req2 && (kind2 != 2'b11);
        eligible[3] = req3 && (kind3 != 2'b11);

        w_exists = 1'b0;
        w        = 2'b00;
        if (eligible[(last + 1) % 4]) begin w_exists = 1'b1; w = (last + 1) % 4; end
        else if (eligible[(last + 2) % 4]) begin w_exists = 1'b1; w = (last + 2) % 4; end
        else if (eligible[(last + 3) % 4]) begin w_exists = 1'b1; w = (last + 3) % 4; end
        else if (eligible[last]) begin w_exists = 1'b1; w = last; end

        case (w)
            2'd0: kw = kind0;
            2'd1: kw = kind1;
            2'd2: kw = kind2;
            2'd3: kw = kind3;
            default: kw = 2'b00;
        endcase

        cstore = w_exists && (kw == 2'b00) && is_ram && c_store && !c_amo;
        camo   = w_exists && (kw == 2'b00) && is_ram && c_amo;
        cload  = w_exists && (kw == 2'b00) && is_ram && !c_store && !c_amo;
        dev    = w_exists && (kw == 2'b00) && !is_ram;
        start  = (cstore || camo || cload || (w_exists && (kw == 2'b01)) || (w_exists && (kw == 2'b10))) && eng_ready;
    end

    always @* begin
        sel0 = 1'b0; sel1 = 1'b0; sel2 = 1'b0; sel3 = 1'b0;
        bsel0 = 1'b0; bsel1 = 1'b0; bsel2 = 1'b0; bsel3 = 1'b0;
        grant0 = 1'b0; grant1 = 1'b0; grant2 = 1'b0; grant3 = 1'b0;
        eng_start = 1'b0; eng_we = 1'b0; eng_line = 1'b0; eng_src = 2'b00;
        rdone = 1'b0; wdone = 1'b0;

        next_state = state;
        next_cur = cur;
        next_core = core;
        next_last = last;

        case (state)
            S_IDLE: begin
                if (w_exists) begin
                    case (w)
                        2'd0: sel0 = 1'b1;
                        2'd1: sel1 = 1'b1;
                        2'd2: sel2 = 1'b1;
                        2'd3: sel3 = 1'b1;
                    endcase
                    if (kw == 2'b00) begin
                        case (w)
                            2'd0: bsel0 = 1'b1;
                            2'd1: bsel1 = 1'b1;
                            2'd2: bsel2 = 1'b1;
                            2'd3: bsel3 = 1'b1;
                        endcase
                    end
                    if (dev) begin
                        case (w)
                            2'd0: grant0 = 1'b1;
                            2'd1: grant1 = 1'b1;
                            2'd2: grant2 = 1'b1;
                            2'd3: grant3 = 1'b1;
                        endcase
                    end
                    eng_start = start;
                    eng_we    = start && cstore;
                    eng_line  = start && (kw == 2'b10);
                    eng_src   = w_exists ? kw : 2'b00;
                end else begin
                    eng_src = 2'b00;
                end

                if (start) begin
                    next_cur   = w;
                    next_last  = w;
                    next_core  = (kw == 2'b00);
                    if (cstore)       next_state = S_WRITE_WAIT;
                    else if (camo)    next_state = S_ATOMIC_READ_WAIT;
                    else              next_state = S_READ_WAIT;
                end else if (dev) begin
                    next_last = w;
                end
            end

            S_READ_WAIT: begin
                case (cur)
                    2'd0: begin sel0 = 1'b1; if (core) bsel0 = 1'b1; end
                    2'd1: begin sel1 = 1'b1; if (core) bsel1 = 1'b1; end
                    2'd2: begin sel2 = 1'b1; if (core) bsel2 = 1'b1; end
                    2'd3: begin sel3 = 1'b1; if (core) bsel3 = 1'b1; end
                endcase
                if (eng_done) begin
                    case (cur)
                        2'd0: grant0 = 1'b1;
                        2'd1: grant1 = 1'b1;
                        2'd2: grant2 = 1'b1;
                        2'd3: grant3 = 1'b1;
                    endcase
                end
                rdone = eng_done;
                if (eng_done) next_state = S_IDLE;
            end

            S_WRITE_WAIT: begin
                case (cur)
                    2'd0: begin sel0 = 1'b1; if (core) bsel0 = 1'b1; end
                    2'd1: begin sel1 = 1'b1; if (core) bsel1 = 1'b1; end
                    2'd2: begin sel2 = 1'b1; if (core) bsel2 = 1'b1; end
                    2'd3: begin sel3 = 1'b1; if (core) bsel3 = 1'b1; end
                endcase
                if (eng_done) begin
                    case (cur)
                        2'd0: grant0 = 1'b1;
                        2'd1: grant1 = 1'b1;
                        2'd2: grant2 = 1'b1;
                        2'd3: grant3 = 1'b1;
                    endcase
                end
                wdone = eng_done;
                if (eng_done) next_state = S_IDLE;
            end

            S_ATOMIC_READ_WAIT: begin
                case (cur)
                    2'd0: begin sel0 = 1'b1; if (core) bsel0 = 1'b1; end
                    2'd1: begin sel1 = 1'b1; if (core) bsel1 = 1'b1; end
                    2'd2: begin sel2 = 1'b1; if (core) bsel2 = 1'b1; end
                    2'd3: begin sel3 = 1'b1; if (core) bsel3 = 1'b1; end
                endcase
                rdone = eng_done;
                if (eng_done) next_state = S_ATOMIC_DECIDE;
            end

            S_ATOMIC_DECIDE: begin
                case (cur)
                    2'd0: begin sel0 = 1'b1; if (core) bsel0 = 1'b1; end
                    2'd1: begin sel1 = 1'b1; if (core) bsel1 = 1'b1; end
                    2'd2: begin sel2 = 1'b1; if (core) bsel2 = 1'b1; end
                    2'd3: begin sel3 = 1'b1; if (core) bsel3 = 1'b1; end
                endcase
                eng_start = c_dmem_we && eng_ready;
                eng_we    = c_dmem_we && eng_ready;
                eng_line  = 1'b0;
                eng_src   = 2'b00;
                if (!c_dmem_we) begin
                    case (cur)
                        2'd0: grant0 = 1'b1;
                        2'd1: grant1 = 1'b1;
                        2'd2: grant2 = 1'b1;
                        2'd3: grant3 = 1'b1;
                    endcase
                end
                if (c_dmem_we && eng_ready)       next_state = S_ATOMIC_WRITE_WAIT;
                else if (!c_dmem_we)              next_state = S_IDLE;
                else                              next_state = S_ATOMIC_DECIDE;
            end

            S_ATOMIC_WRITE_WAIT: begin
                case (cur)
                    2'd0: begin sel0 = 1'b1; if (core) bsel0 = 1'b1; end
                    2'd1: begin sel1 = 1'b1; if (core) bsel1 = 1'b1; end
                    2'd2: begin sel2 = 1'b1; if (core) bsel2 = 1'b1; end
                    2'd3: begin sel3 = 1'b1; if (core) bsel3 = 1'b1; end
                endcase
                if (eng_done) begin
                    case (cur)
                        2'd0: grant0 = 1'b1;
                        2'd1: grant1 = 1'b1;
                        2'd2: grant2 = 1'b1;
                        2'd3: grant3 = 1'b1;
                    endcase
                end
                wdone = eng_done;
                if (eng_done) next_state = S_IDLE;
            end

            default: begin
                next_state = S_IDLE;
            end
        endcase
    end

    always @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            cur   <= 2'b00;
            core  <= 1'b0;
            last  <= 2'b11;
        end else begin
            state <= next_state;
            cur   <= next_cur;
            core  <= next_core;
            last  <= next_last;
        end
    end

endmodule
