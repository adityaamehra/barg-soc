module pmp_regs16 (
    input          clk,
    input          rst,
    input          we,
    input  [31:0]  inst,
    input  [5:0]   sel,
    input  [31:0]  nval,
    output [31:0]  rdata,
    output [127:0] cfg_all,
    output [511:0] addr_all
);

    reg [7:0]  cfg  [0:15];
    reg [31:0] addr [0:15];

    wire [11:0] a;
    wire        wr;
    reg  [31:0] rdata_r;

    integer i, j;

    assign a  = inst[31:20];
    assign wr = we && ((sel == 6'd42) || (sel == 6'd43) || (sel == 6'd45));
    assign rdata = rdata_r;

    genvar g;
    generate
        for (g = 0; g < 16; g = g + 1) begin : gen_cfg_out
            assign cfg_all[8*g + 7 : 8*g] = cfg[g];
        end
        for (g = 0; g < 16; g = g + 1) begin : gen_addr_out
            assign addr_all[32*g + 31 : 32*g] = addr[g];
        end
    endgenerate

    always @(posedge clk) begin
        if (rst) begin
            for (i = 0; i < 16; i = i + 1) begin
                cfg[i]  <= 8'd0;
                addr[i] <= 32'd0;
            end
        end else begin
            if (wr) begin
                for (i = 0; i < 4; i = i + 1) begin
                    if (a == (12'h3A0 + i[11:0])) begin
                        for (j = 0; j < 4; j = j + 1) begin
                            if (cfg[i*4 + j][7] == 1'b1) begin
                                cfg[i*4 + j] <= cfg[i*4 + j];
                            end else if ((nval[8*j + 0] == 1'b0) && (nval[8*j + 1] == 1'b1)) begin
                                cfg[i*4 + j] <= cfg[i*4 + j];
                            end else begin
                                cfg[i*4 + j] <= nval[8*j +: 8] & 8'h9F;
                            end
                        end
                    end
                end
                for (i = 0; i < 16; i = i + 1) begin
                    if (a == (12'h3B0 + i[11:0])) begin
                        if (cfg[i][7] == 1'b1) begin
                            addr[i] <= addr[i];
                        end else if ((i < 15) && (cfg[i+1][7] == 1'b1) && (cfg[i+1][4:3] == 2'b01)) begin
                            addr[i] <= addr[i];
                        end else begin
                            addr[i] <= nval;
                        end
                    end
                end
            end
        end
    end

    always @* begin
        rdata_r = 32'd0;
        if ((a >= 12'h3A0) && (a <= 12'h3A3)) begin
            rdata_r = {cfg[{a[1:0], 2'b11}],
                       cfg[{a[1:0], 2'b10}],
                       cfg[{a[1:0], 2'b01}],
                       cfg[{a[1:0], 2'b00}]};
        end else if ((a >= 12'h3B0) && (a <= 12'h3BF)) begin
            rdata_r = addr[a[3:0]];
        end
    end

endmodule
