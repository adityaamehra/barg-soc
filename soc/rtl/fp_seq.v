module fp_seq (
    input  wire        clk,
    input  wire        rst,
    input  wire        is_fpu,
    input  wire        done,
    input  wire [63:0] fres_in,
    input  wire [31:0] ires_in,
    input  wire [4:0]  flags_in,
    input  wire        wrf_in,
    output wire        start,
    output wire        busy,
    output wire [63:0] fres,
    output wire [31:0] ires,
    output wire [4:0]  flags,
    output wire        wrf
);

    reg [1:0] st;
    reg [63:0] fres_reg;
    reg [31:0] ires_reg;
    reg [4:0]  flags_reg;
    reg        wrf_reg;

    assign start = is_fpu & (st == 2'b00);
    assign busy  = is_fpu & (st != 2'b10);
    assign fres  = fres_reg;
    assign ires  = ires_reg;
    assign flags = flags_reg;
    assign wrf   = wrf_reg;

    always @(posedge clk) begin
        if (rst) begin
            st        <= 2'b00;
            fres_reg  <= 64'b0;
            ires_reg  <= 32'b0;
            flags_reg <= 5'b0;
            wrf_reg   <= 1'b0;
        end else begin
            case (st)
                2'b00: if (is_fpu) st <= 2'b01;
                2'b01: if (done) begin
                           fres_reg  <= fres_in;
                           ires_reg  <= ires_in;
                           flags_reg <= flags_in;
                           wrf_reg   <= wrf_in;
                           st        <= 2'b10;
                       end
                2'b10: st <= 2'b00;
                default: st <= 2'b00;
            endcase
        end
    end

endmodule
