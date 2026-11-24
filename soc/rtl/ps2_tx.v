module ps2_tx(
    input  clk,
    input  rst,
    input  clk_i,
    input  dat_i,
    input  start,
    input  [7:0] data,
    output clk_low,
    output dat_low,
    output busy,
    output done,
    output err
);

// Internal registers
reg c1, c2, c3;
reg d1, d2;
reg [1:0] st;          // 0 idle, 1 inhibit, 2 sending
reg [13:0] hold;
reg [3:0] n;
reg [8:0] sh;          // 8 data bits + parity
reg done_reg;
reg err_reg;

// Edge detection
wire fall = c3 & ~c2;
wire rise = ~c3 & c2;

// Reset logic (synchronous)
always @(posedge clk or posedge rst) begin
    if (rst) begin
        c1 <= 1'b1;
        c2 <= 1'b1;
        c3 <= 1'b1;
        d1 <= 1'b1;
        d2 <= 1'b1;
        st <= 2'b00;
        hold <= 14'd0;
        n <= 4'd0;
        sh <= 9'd0;
        done_reg <= 1'b0;
        err_reg <= 1'b0;
    end else begin
        // Shift registers for clock and data lines
        c1 <= clk_i;
        c2 <= c1;
        c3 <= c2;
        d1 <= dat_i;
        d2 <= d1;

        // State machine
        case (st)
            2'b00: begin // idle
                done_reg <= 1'b0;
                if (start) begin
                    // Load shift register with data and parity
                    sh <= {~(^data), data}; // parity bit: 1 when even number of ones
                    hold <= 14'd0;
                    err_reg <= 1'b0;
                    st <= 2'b01;
                end
            end
            2'b01: begin // inhibit
                hold <= hold + 14'd1;
                if (hold == 14'd16383) begin
                    st <= 2'b10;
                    n <= 4'd0;
                end
            end
            2'b10: begin // sending
                if (fall) begin
                    n <= n + 4'd1;
                end
                if (n == 4'd12 && rise) begin
                    done_reg <= 1'b1;
                    err_reg <= d2; // 1 if device did not acknowledge
                    st <= 2'b00;
                end
            end
            default: st <= 2'b00;
        endcase
    end
end

// Combinational outputs
assign clk_low = (st == 2'b01) ? 1'b1 : 1'b0;

assign dat_low = (st == 2'b10) ?
                 ((n == 4'd0 || n == 4'd1) ? 1'b1 :
                  ((n >= 4'd2 && n <= 4'd10) ? ~sh[n-4'd2] : 1'b0))
                 : 1'b0;

assign busy = (st != 2'b00);
assign done = done_reg;
assign err  = err_reg;

endmodule
