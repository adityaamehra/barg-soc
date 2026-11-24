module spi_regs(
    input  clk,
    input  rst,
    input  we,
    input  [31:0] addr,
    input  [31:0] wdata,
    input  tx_ready,
    input  [7:0] rx_data,
    input  rx_valid,
    output [31:0] rdata,
    output [7:0]  tx_data,
    output [1:0]  tx_cs,
    output        tx_valid,
    output        irq
);

// Internal registers
reg  [1:0] cs_reg;
reg  [7:0] last_reg;
reg        done_reg;
reg        busy_reg;
reg        ien_reg;

// Combinational outputs
assign tx_data  = wdata[7:0];
assign tx_cs    = cs_reg;
assign tx_valid = we & (addr[4:2] == 3'b000) & tx_ready;
assign irq      = done_reg & ien_reg;

// rdata combinational logic
wire [2:0] addr_bits = addr[4:2];
assign rdata = (addr_bits == 3'b000) ? {24'b0, last_reg} :
               (addr_bits == 3'b001) ? {30'b0, done_reg, busy_reg} :
               (addr_bits == 3'b010) ? {30'b0, cs_reg} :
               (addr_bits == 3'b011) ? {31'b0, ien_reg} :
               32'b0;

// Sequential logic
always @(posedge clk) begin
    if (rst) begin
        cs_reg   <= 2'b0;
        last_reg <= 8'b0;
        done_reg <= 1'b0;
        busy_reg <= 1'b0;
        ien_reg  <= 1'b0;
    end else begin
        // Handle rx_valid priority
        if (rx_valid) begin
            busy_reg <= 1'b0;
            done_reg <= 1'b1;
            last_reg <= rx_data;
        end else begin
            // rx_valid == 0
            if (tx_valid) begin
                busy_reg <= 1'b1;
            end
            // Clear done on write to bit1 of wdata when addr[4:2]==1
            if (we && (addr[4:2] == 3'b001) && wdata[1]) begin
                done_reg <= 1'b0;
            end
        end

        // Write cs
        if (we && (addr[4:2] == 3'b010)) begin
            cs_reg <= wdata[1:0];
        end

        // Write ien
        if (we && (addr[4:2] == 3'b011)) begin
            ien_reg <= wdata[0];
        end
    end
end

endmodule
