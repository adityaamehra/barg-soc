module ps2_rx(
    input  clk,          // system clock
    input  rst,          // synchronous reset
    input  clk_i,        // PS/2 clock line
    input  dat_i,        // PS/2 data line
    output reg  valid,   // data ready
    output reg [7:0] dout, // received byte
    output reg  perr     // parity / framing error
);

// Internal registers
reg          c1, c2, c3;          // clock synchronizer (3 FFs)
reg          d1, d2;              // data synchronizer (2 FFs)
reg  [3:0]   cnt;                 // bit counter (0..10)
reg  [10:0]  sh;                  // shift register for bits 0..10
reg  [15:0]  idle;                // cycles since last falling edge (max 65535)

wire fall = c3 & ~c2;              // falling edge of PS/2 clock

// Synchronous logic
always @(posedge clk) begin
    if (rst) begin
        // Reset all state
        c1 <= 1'b1; c2 <= 1'b1; c3 <= 1'b1;
        d1 <= 1'b1; d2 <= 1'b1;
        cnt <= 4'd0;
        sh  <= 11'd0;
        idle <= 16'd0;
        valid <= 1'b0;
        perr  <= 1'b0;
        dout  <= 8'd0;
    end else begin
        // Clear outputs each cycle unless set below
        valid <= 1'b0;
        perr  <= 1'b0;

        // Synchronizers
        c1 <= clk_i;
        c2 <= c1;
        c3 <= c2;
        d1 <= dat_i;
        d2 <= d1;

        // Idle counter
if (fall) begin
    idle <= 16'd0;
end else if (idle != 16'd65535) begin
    idle <= idle + 16'd1;
end

        // Bit counter and shift register
if (fall) begin
    if (idle == 16'd32767) begin
        // Frame stalled: drop current frame
        cnt <= 4'd0;
    end else if (cnt == 4'd10) begin
        // Last bit received: evaluate frame
        cnt <= 4'd0;
        if (sh[0] == 1'b0 && d2 == 1'b1 && (^sh[9:1]) == 1'b1) begin
            // Valid frame
            valid <= 1'b1;
            dout  <= sh[8:1];
        end else begin
            // Error
            perr <= 1'b1;
        end
    end else begin
        // Shift in the received bit
        cnt <= cnt + 4'd1;
        sh  <= (sh & ~(11'd1 << cnt)) | ({10'd0, d2} << cnt);
    end
end else begin
    if (idle == 16'd32767) begin
        cnt <= 4'd0;
    end
end
        // When no falling edge, cnt and sh remain unchanged
    end
end

endmodule
