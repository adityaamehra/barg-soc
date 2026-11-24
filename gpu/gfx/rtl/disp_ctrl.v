module disp_ctrl (
    input  wire        clk,
    input  wire        rst,
    input  wire        enable,
    input  wire [15:0] vd_rdata0,
    input  wire [15:0] vd_rdata1,
    input  wire [15:0] vd_rdata2,
    input  wire [15:0] vd_rdata3,
    output wire [14:0] vd_raddr,
    output wire        hsync,
    output wire        vsync,
    output wire        de,
    output wire [15:0] rgb,
    output wire        vblank,
    output wire [7:0]  frame
);

    reg [9:0]  hc, vc;
    reg [7:0]  frame_r;
    reg [9:0]  d_hc, d_vc;
    reg        d_on;

    wire [14:0] addr_vis = (vc >> 1) * 10'd80 + (hc >> 3);
    assign vd_raddr = (hc < 10'd640 && vc < 10'd480) ? addr_vis : 15'd0;

    assign vblank = (vc >= 10'd480);
    assign frame  = frame_r;

    wire vis = d_on & (d_hc < 10'd640) & (d_vc < 10'd480);
    assign de = vis;

    reg [15:0] rgb_sel;
    always @* begin
        case ((d_hc >> 1) & 3)
            2'd0: rgb_sel = vd_rdata0;
            2'd1: rgb_sel = vd_rdata1;
            2'd2: rgb_sel = vd_rdata2;
            default: rgb_sel = vd_rdata3;
        endcase
    end
    assign rgb = vis ? rgb_sel : 16'd0;

    assign hsync = (d_on && (d_hc >= 10'd656) && (d_hc < 10'd752)) ? 1'b0 : 1'b1;
    assign vsync = (d_on && (d_vc >= 10'd490) && (d_vc < 10'd492)) ? 1'b0 : 1'b1;

    always @(posedge clk) begin
        if (rst) begin
            hc      <= 10'd0;
            vc      <= 10'd0;
            frame_r <= 8'd0;
            d_hc    <= 10'd0;
            d_vc    <= 10'd0;
            d_on    <= 1'b0;
        end else if (!enable) begin
            hc   <= 10'd0;
            vc   <= 10'd0;
            d_on <= 1'b0;
        end else begin
            d_hc <= hc;
            d_vc <= vc;
            d_on <= 1'b1;
            if (hc == 10'd799) begin
                hc <= 10'd0;
                if (vc == 10'd524) begin
                    vc      <= 10'd0;
                    frame_r <= frame_r + 8'd1;
                end else begin
                    vc <= vc + 10'd1;
                end
            end else begin
                hc <= hc + 10'd1;
            end
        end
    end

endmodule
