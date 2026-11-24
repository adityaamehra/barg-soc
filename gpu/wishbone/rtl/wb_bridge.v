module wb_bridge (
    input  wire        clk,
    input  wire        rst,
    input  wire        wb_cyc,
    input  wire        wb_stb,
    input  wire        wb_we,
    input  wire [3:0]  wb_sel,
    input  wire [31:0] wb_adr,
    input  wire [31:0] wb_dat_i,
    input  wire [31:0] host_rdata,
    input  wire        host_rvalid,
    output wire        wb_ack,
    output wire [31:0] wb_dat_o,
    output wire        host_en,
    output wire        host_we,
    output wire [31:0] host_addr,
    output wire [31:0] host_wdata
);

    reg [1:0]  state;
    reg        we_r;
    reg [31:0] addr_r;
    reg [31:0] wdata_r;
    reg [31:0] rdata_r;

    assign host_en    = (state == 2'd1);
    assign host_we    = (state == 2'd1) & we_r;
    assign host_addr  = addr_r;
    assign host_wdata = wdata_r;
    assign wb_ack     = (state == 2'd3);
    assign wb_dat_o   = rdata_r;

    wire        accept = wb_cyc & wb_stb;
    wire        adr_valid = (wb_adr[31:20] == 12'h300) & (wb_adr[1:0] == 2'b00);
    wire [3:0]  window = wb_adr[19:16];
    wire [15:0] off = wb_adr[15:0];

    wire win0 = (window == 4'd0);
    wire win1 = (window == 4'd1) & (off[15:11] == 5'b00000);
    wire win2 = (window == 4'd2) & (off[15:13] == 3'b000);
    wire win3 = (window == 4'd3) & (off[15:12] == 4'b0000);
    wire mapped = win0 | win1 | win2 | win3;

    wire [31:0] host_addr_c =
        win0 ? (32'h3000_0000 | {16'd0, off}) :
        win1 ? {21'd0, off[10:0]} :
        win2 ? (32'h1000_0000 | {19'd0, off[12:0]}) :
               (32'h2000_0000 | {20'd0, off[11:0]});

    wire go = accept & adr_valid & mapped & (wb_we ? (wb_sel == 4'b1111) : 1'b1);

    always @(posedge clk) begin
        if (rst) begin
            state   <= 2'd0;
            we_r    <= 1'b0;
            addr_r  <= 32'd0;
            wdata_r <= 32'd0;
            rdata_r <= 32'd0;
        end else begin
            case (state)
                2'd0: begin // IDLE
                    if (accept) begin
                        we_r    <= wb_we;
                        wdata_r <= wb_dat_i;
                        rdata_r <= 32'd0;
                        if (go) begin
                            addr_r <= host_addr_c;
                            state  <= 2'd1;
                        end else begin
                            state <= 2'd3;
                        end
                    end
                end
                2'd1: begin // REQ
                    state <= we_r ? 2'd3 : 2'd2;
                end
                2'd2: begin // WAIT
                    if (host_rvalid) begin
                        rdata_r <= host_rdata;
                        state   <= 2'd3;
                    end
                end
                2'd3: begin // DONE
                    state <= 2'd0;
                end
                default: state <= 2'd0;
            endcase
        end
    end

endmodule
