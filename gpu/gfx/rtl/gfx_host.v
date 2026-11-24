module gfx_host (
    input wire clk,
    input wire rst,
    input wire host_en,
    input wire host_we,
    input wire [31:0] host_addr,
    input wire [31:0] host_wdata,
    input wire [31:0] core_rdata,
    input wire [15:0] vw_rdata0,
    input wire [15:0] vw_rdata1,
    input wire [15:0] vw_rdata2,
    input wire [15:0] vw_rdata3,
    input wire vblank,
    input wire [7:0] frame,
    output wire v_we0,
    output wire v_we1,
    output wire v_we2,
    output wire v_we3,
    output wire [14:0] v_waddr,
    output wire [15:0] v_wdata_lo,
    output wire [15:0] v_wdata_hi,
    output wire [14:0] vw_raddr,
    output wire [31:0] host_rdata,
    output reg disp_en
);
    reg [31:0] raddr;

    wire host_in_win;
    wire raddr_in_win;
    wire wr;
    wire [31:0] vwin_rdata;

    assign host_in_win = (host_addr[31:18] == 14'h1000) &&
                         (host_addr[17:0] < 18'h25800) &&
                         (host_addr[1:0] == 2'b00);

    assign raddr_in_win = (raddr[31:18] == 14'h1000) &&
                          (raddr[17:0] < 18'h25800) &&
                          (raddr[1:0] == 2'b00);

    assign wr = host_en & host_we & host_in_win;

    assign v_we0 = wr & ~host_addr[2];
    assign v_we1 = wr & ~host_addr[2];
    assign v_we2 = wr & host_addr[2];
    assign v_we3 = wr & host_addr[2];

    assign v_waddr = host_addr[17:3];
    assign v_wdata_lo = host_wdata[15:0];
    assign v_wdata_hi = host_wdata[31:16];
    assign vw_raddr = host_addr[17:3];

    assign vwin_rdata = raddr[2] ? {vw_rdata3, vw_rdata2} : {vw_rdata1, vw_rdata0};

    assign host_rdata = raddr_in_win ? vwin_rdata :
                        (raddr == 32'h3000_0020) ? {31'b0, disp_en} :
                        (raddr == 32'h3000_0024) ? {16'b0, frame[7:0], 7'b0, vblank} :
                        core_rdata;

    always @(posedge clk) begin
        if (rst) begin
            raddr <= 32'd0;
            disp_en <= 1'b0;
        end else begin
            raddr <= host_addr;
            if (host_en & host_we & (host_addr == 32'h3000_0020))
                disp_en <= host_wdata[0];
        end
    end
endmodule
