module gpio_regs(
    input          clk,
    input          rst,
    input          we,
    input  [31:0]  addr,
    input  [31:0]  wdata,
    input  [15:0]  pins,
    output [31:0]  rdata,
    output [15:0]  gpio_out,
    output [15:0]  gpio_oe,
    output         irq
);
    // Registers
    reg  [15:0] out;
    reg  [15:0] oe;
    reg  [15:0] ien;
    reg  [15:0] pend;
    reg  [15:0] s1;
    reg  [15:0] s2;
    reg  [15:0] prev;

    // Combinational signals
    wire [15:0] rise;
    wire [15:0] clr;

    assign rise = s2 & ~prev;
    assign clr  = (we && (addr[3:2] == 2'b11)) ? wdata[15:0] : 16'd0;

    // Sequential logic
    always @(posedge clk) begin
        if (rst) begin
            out  <= 16'd0;
            oe   <= 16'd0;
            ien  <= 16'd0;
            pend <= 16'd0;
            s1   <= 16'd0;
            s2   <= 16'd0;
            prev <= 16'd0;
        end else begin
            // Sample pins
            s1   <= pins;
            s2   <= s1;
            prev <= s2;

            // Update pend
            pend <= (pend & ~clr) | rise;

            // Write registers
            if (we) begin
                case (addr[3:2])
                    2'b00: out  <= wdata[15:0];
                    2'b01: oe   <= wdata[15:0];
                    2'b10: ien  <= wdata[15:0];
                    default: ; // pend handled by clr
                endcase
            end
        end
    end

    // Combinational outputs
    assign rdata   = (addr[3:2] == 2'b00) ? {16'd0, s2} :
                     (addr[3:2] == 2'b01) ? {16'd0, oe}  :
                     (addr[3:2] == 2'b10) ? {16'd0, ien} :
                                            {16'd0, pend};

    assign gpio_out = out;
    assign gpio_oe  = oe;
    assign irq      = |(pend & ien);

endmodule
