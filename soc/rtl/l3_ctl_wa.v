module l3_ctl_wa (
    input  clk,
    input  rst,
    input  rv,
    input  rwe,
    input  rline,
    input  [31:0] raddr,
    input  [31:0] rwdata,
    input  [3:0]  rwstrb,
    input  hit,
    input  [255:0] lk_line,
    input  vic_valid,
    input  vic_dirty,
    input  [31:0] vic_addr,
    input  [255:0] vic_data,
    input  ax_ready,
    input  ax_done,
    input  [255:0] ax_data,
    output ready,
    output resp_valid,
    output [255:0] resp_data,
    output [31:0] lk_addr,
    output fill_en,
    output [31:0] fill_addr,
    output [255:0] fill_data,
    output wr_en,
    output [31:0] wr_addr,
    output [31:0] wr_data,
    output [3:0] wr_be,
    output ax_valid,
    output ax_we,
    output ax_line,
    output [31:0] ax_addr,
    output [31:0] ax_wdata,
    output [3:0] ax_wstrb,
    output [255:0] ax_wline
);

// State encoding
localparam IDLE = 4'd0,
           LOOK = 4'd1,
           WBREQ = 4'd2,
           WBWAIT = 4'd3,
           FREQ = 4'd4,
           FWAIT = 4'd5,
           FILL = 4'd6,
           WR = 4'd7,
           AREQ = 4'd8,
           AWAIT = 4'd9,
           RESP = 4'd10;

// Registers
reg [3:0] state;
reg we_q;
reg line_q;
reg [31:0] addr_q;
reg [31:0] wd_q;
reg [3:0] ws_q;

// Sequential logic: state machine and held registers
always @(posedge clk) begin
    if (rst) begin
        state <= IDLE;
        we_q <= 1'b0;
        line_q <= 1'b0;
        addr_q <= 32'd0;
        wd_q <= 32'd0;
        ws_q <= 4'd0;
    end else begin
        // Default: hold current state
        state <= state;
        // State transitions
        case (state)
            IDLE: begin
                if (rv) begin
                    we_q <= rwe;
                    line_q <= rline;
                    addr_q <= raddr;
                    wd_q <= rwdata;
                    ws_q <= rwstrb;
                    state <= LOOK;
                end
            end
            LOOK: begin
                if (!we_q) begin // read
                    if (hit) state <= RESP;
                    else if (vic_valid && vic_dirty) state <= WBREQ;
                    else state <= FREQ;
                end else begin // write
                    if (hit) state <= WR;
                    else if (vic_valid && vic_dirty) state <= WBREQ;
                    else state <= FREQ;
                end
            end
            WBREQ: begin
                if (ax_ready) state <= WBWAIT;
            end
            WBWAIT: begin
                if (ax_done) state <= FREQ;
            end
            FREQ: begin
                if (ax_ready) state <= FWAIT;
            end
            FWAIT: begin
                if (ax_done) state <= FILL;
            end
            FILL: begin
                if (we_q) state <= WR;
                else state <= RESP;
            end
            WR: begin
                state <= RESP;
            end
            AREQ: begin
                if (ax_ready) state <= AWAIT;
            end
            AWAIT: begin
                if (ax_done) state <= RESP;
            end
            RESP: begin
                state <= IDLE;
            end
            default: begin
                state <= IDLE;
            end
        endcase
    end
end

// Combinational outputs
assign ready = (state == IDLE);

assign resp_valid = (state == RESP);

assign resp_data = (state == RESP) ?
    (we_q ? 256'd0 :
        (line_q ? lk_line :
            {224'd0, lk_line[(addr_q[4:2]+1)*32-1 -: 32]})) :
    256'd0;

assign lk_addr = addr_q;

assign fill_en = (state == FILL);
assign fill_addr = addr_q;
assign fill_data = ax_data;

assign wr_en = (state == WR);
assign wr_addr = addr_q;
assign wr_data = wd_q;
assign wr_be = ws_q;

assign ax_valid = (state == WBREQ) || (state == FREQ) || (state == AREQ);
assign ax_we = (state == WBREQ) || (state == AREQ);
assign ax_line = (state == WBREQ) || (state == FREQ);

assign ax_addr = (state == WBREQ) ? vic_addr :
                 (state == FREQ) ? (addr_q & ~32'h1F) :
                 (state == AREQ) ? (addr_q & ~32'h3) :
                 32'd0;

assign ax_wdata = wd_q;
assign ax_wstrb = ws_q;
assign ax_wline = vic_data;

endmodule
