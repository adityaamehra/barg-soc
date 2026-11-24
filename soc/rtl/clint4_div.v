module clint4_div (
    input clk,
    input rst,
    input [2:0] kind,
    input [1:0] hart,
    input [31:0] wdata,
    input we,
    output reg [31:0] rdata,
    output [63:0] mtime,
    output mtip0,
    output mtip1,
    output mtip2,
    output mtip3,
    output msip0,
    output msip1,
    output msip2,
    output msip3
);

    reg [3:0] msip_reg;
    reg [63:0] mtime_reg;
    reg [63:0] mtimecmp_reg [0:3];
    reg [3:0] pre;

    assign msip0 = msip_reg[0];
    assign msip1 = msip_reg[1];
    assign msip2 = msip_reg[2];
    assign msip3 = msip_reg[3];

    assign mtime = mtime_reg;

    assign mtip0 = (mtime_reg >= mtimecmp_reg[0]);
    assign mtip1 = (mtime_reg >= mtimecmp_reg[1]);
    assign mtip2 = (mtime_reg >= mtimecmp_reg[2]);
    assign mtip3 = (mtime_reg >= mtimecmp_reg[3]);

    always @(posedge clk) begin
        if (rst) begin
            pre <= 4'b0;
            msip_reg <= 4'b0;
            mtime_reg <= 64'b0;
            mtimecmp_reg[0] <= 64'hFFFFFFFFFFFFFFFF;
            mtimecmp_reg[1] <= 64'hFFFFFFFFFFFFFFFF;
            mtimecmp_reg[2] <= 64'hFFFFFFFFFFFFFFFF;
            mtimecmp_reg[3] <= 64'hFFFFFFFFFFFFFFFF;
        end else begin
            // Increment prescaler
            pre <= (pre == 4'd15) ? 4'd0 : pre + 1;

            // Write logic
            if (we) begin
                case (kind)
                    3'd1: begin
                        msip_reg[hart] <= wdata[0];
                    end
                    3'd2: begin
                        mtimecmp_reg[hart][31:0] <= wdata;
                    end
                    3'd3: begin
                        mtimecmp_reg[hart][63:32] <= wdata;
                    end
                    3'd4: begin
                        mtime_reg[31:0] <= wdata;
                    end
                    3'd5: begin
                        mtime_reg[63:32] <= wdata;
                    end
                    default: begin
                        // no write
                    end
                endcase
            end

            // Increment mtime only when pre==15 before the edge and not writing to mtime halves
            if ((pre == 4'd15) && !(we && (kind==4 || kind==5))) begin
                mtime_reg <= mtime_reg + 1;
            end
        end
    end

    always @* begin
        case (kind)
            3'd1: rdata = {31'b0, msip_reg[hart]};
            3'd2: rdata = mtimecmp_reg[hart][31:0];
            3'd3: rdata = mtimecmp_reg[hart][63:32];
            3'd4: rdata = mtime_reg[31:0];
            3'd5: rdata = mtime_reg[63:32];
            default: rdata = 32'b0;
        endcase
    end

endmodule
