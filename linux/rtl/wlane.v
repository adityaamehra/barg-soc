module wlane (
    input [3:0] memtype,
    input [31:0] addr,
    input [31:0] wdata,
    output reg [3:0] be,
    output reg [31:0] data
);

    always @* begin
        case (memtype)
            // Byte access (000, 011)
            4'd0, 4'd3: begin
                // a = bits 1:0 of addr
                // be has only bit a set
                be = 4'b0001 << addr[1:0];
                // data is bits 7:0 of wdata shifted left by 8 * a
                data = wdata[7:0] << (8 * addr[1:0]);
            end

            // Half-word access (001, 100)
            4'd1, 4'd4: begin
                // h = bit 1 of addr
                // be is 0011 when h=0 and 1100 when h=1
                be = addr[1] ? 4'b1100 : 4'b0011;
                // data is bits 15:0 of wdata shifted left by 16 * h
                data = wdata[15:0] << (16 * addr[1]);
            end

            // Word access (010, 110, 111)
            4'd2, 4'd6, 4'd7: begin
                // be is 1111
                be = 4'b1111;
                // data is wdata
                data = wdata;
            end

            // No access (101)
            4'd5: begin
                // be and data are 0
                be = 4'b0000;
                data = 32'b0;
            end

            // Handle reserved/unspecified codes if necessary, though the description implies 0-7 are covered.
            default: begin
                // Defaulting to no access for safety, although all 8 codes are defined above.
                be = 4'b0000;
                data = 32'b0;
            end
        endcase
    end

endmodule
