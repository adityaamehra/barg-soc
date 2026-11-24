module disp_regs(
    input        clk,
    input        rst,
    input        we,
    input  [31:0] addr,
    input  [31:0] wdata,
    input        frame,
    input        vbl,
    output [31:0] rdata,
    output        enable
);

    reg          en;
    reg  [31:0]  frames;

    // Synchronous reset and register updates
    always @(posedge clk) begin
        if (rst) begin
            en     <= 1'b0;
            frames <= 32'd0;
        end else begin
            if (we && addr[3:2] == 2'b00) begin
                en <= wdata[0];
            end
            if (frame) begin
                frames <= frames + 32'd1;
            end
        end
    end

    // Combinational read data
    assign rdata = (addr[3:2] == 2'b00) ? {23'd0, vbl, 7'd0, en} :
                   (addr[3:2] == 2'b01) ? 32'h00F00140 :
                   (addr[3:2] == 2'b10) ? frames :
                   32'd0;

    // Enable output
    assign enable = en;

endmodule
