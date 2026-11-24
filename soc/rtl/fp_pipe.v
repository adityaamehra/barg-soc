module fp_pipe (
    input  wire        clk,
    input  wire        rst,
    input  wire        stall_ex,
    input  wire        flush_ex,
    input  wire        flush_mem,
    input  wire        flush_wb,
    input  wire [1:0]  dwsel_id,
    input  wire [63:0] fres_ex,
    input  wire [4:0]  flags_ex,
    input  wire        wrf_ex,
    output reg  [1:0]  dwsel_ex,
    output reg  [1:0]  dwsel_wb,
    output reg  [63:0] fres_wb,
    output reg  [4:0]  flags_wb,
    output reg         wrf_wb
);

    reg [1:0]  dwsel_m;
    reg [63:0] fres_m;
    reg [4:0]  flags_m;
    reg        wrf_m;

    always @(posedge clk) begin
        if (rst || flush_ex) begin
            dwsel_ex <= 2'b00;
        end else if (!stall_ex) begin
            dwsel_ex <= dwsel_id;
        end
    end

    always @(posedge clk) begin
        if (rst || flush_mem) begin
            dwsel_m  <= 2'b00;
            fres_m   <= 64'b0;
            flags_m  <= 5'b0;
            wrf_m    <= 1'b0;
        end else begin
            dwsel_m  <= dwsel_ex;
            fres_m   <= fres_ex;
            flags_m  <= flags_ex;
            wrf_m    <= wrf_ex;
        end
    end

    always @(posedge clk) begin
        if (rst || flush_wb) begin
            dwsel_wb <= 2'b00;
            fres_wb  <= 64'b0;
            flags_wb <= 5'b0;
            wrf_wb   <= 1'b0;
        end else begin
            dwsel_wb <= dwsel_m;
            fres_wb  <= fres_m;
            flags_wb <= flags_m;
            wrf_wb   <= wrf_m;
        end
    end

endmodule
