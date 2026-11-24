module rload (
    input  wire [31:0] word,
    input  wire [2:0]  memtype,
    input  wire [31:0] addr,
    output reg  [31:0] rdata
);

    always @* begin
        // default
        rdata = 32'd0;

        case (memtype)
            3'b000: begin // byte, sign-extended
                case (addr[1:0])
                    2'b00: rdata = {{24{word[7]}},  word[7:0]};
                    2'b01: rdata = {{24{word[15]}}, word[15:8]};
                    2'b10: rdata = {{24{word[23]}}, word[23:16]};
                    2'b11: rdata = {{24{word[31]}}, word[31:24]};
                endcase
            end
            3'b001: begin // half-word, sign-extended
                case (addr[1])
                    1'b0: rdata = {{16{word[15]}},  word[15:0]};
                    1'b1: rdata = {{16{word[31]}},  word[31:16]};
                endcase
            end
            3'b010: begin // word
                rdata = word;
            end
            3'b011: begin // byte, zero-extended
                case (addr[1:0])
                    2'b00: rdata = {24'd0, word[7:0]};
                    2'b01: rdata = {24'd0, word[15:8]};
                    2'b10: rdata = {24'd0, word[23:16]};
                    2'b11: rdata = {24'd0, word[31:24]};
                endcase
            end
            3'b100: begin // half-word, zero-extended
                case (addr[1])
                    1'b0: rdata = {16'd0, word[15:0]};
                    1'b1: rdata = {16'd0, word[31:16]};
                endcase
            end
            3'b101: begin // no access
                rdata = 32'd0;
            end
            3'b110: begin // word
                rdata = word;
            end
            3'b111: begin // word
                rdata = word;
            end
            default: begin
                rdata = 32'd0;
            end
        endcase
    end

endmodule
