module tensor_unit (
    input  wire         clk,
    input  wire         rst,
    input  wire         clear_all,
    input  wire         valid,
    input  wire  [2:0]  unit,
    input  wire         advance,
    input  wire  [1:0]  tensor_op,
    input  wire  [1:0]  wid,
    input  wire  [3:0]  tmask,
    input  wire  [127:0] a,
    input  wire  [127:0] b,
    output wire  [127:0] ld_y,
    output wire         err
);

    localparam TENSOR = 3'b101;

    wire is_t = valid & (unit == TENSOR);
    assign err = is_t & (tmask != 4'b1111);

    // flat accumulator: element 16*wid + 4*i + j
    reg [31:0] acc [0:63];

    integer z;
    initial begin
        for (z = 0; z < 64; z = z + 1) acc[z] = 32'd0;
    end

    // combinational read: lane i gets ACC[wid][i][c], c = lane i of a bits 1:0
    genvar gi;
    generate
        for (gi = 0; gi < 4; gi = gi + 1) begin : g_ld
            wire [1:0] c = a[32*gi +: 2];
            assign ld_y[32*gi +: 32] = acc[16*wid + 4*gi + c];
        end
    endgenerate

    integer i, j, k;
    reg [31:0] sum;
    reg [7:0] av, bv;
    reg [1:0] cs;

    always @(posedge clk) begin
        if (rst | clear_all) begin
            for (z = 0; z < 64; z = z + 1)
                acc[z] <= 32'd0;
        end else if (advance & is_t & !err) begin
            case (tensor_op)
                2'b00: begin // MMA_I8
                    for (i = 0; i < 4; i = i + 1) begin
                        for (j = 0; j < 4; j = j + 1) begin
                            sum = acc[16*wid + 4*i + j];
                            for (k = 0; k < 4; k = k + 1) begin
                                av = a[32*i + 8*k +: 8];
                                bv = b[32*j + 8*k +: 8];
                                sum = sum + {{24{av[7]}}, av} * {{24{bv[7]}}, bv};
                            end
                            acc[16*wid + 4*i + j] <= sum;
                        end
                    end
                end
                2'b01: begin // MMA_LD: nothing changes
                end
                2'b10: begin // MMA_ST
                    for (i = 0; i < 4; i = i + 1) begin
                        cs = b[32*i +: 2];
                        acc[16*wid + 4*i + cs] <= a[32*i +: 32];
                    end
                end
                2'b11: begin // MMA_ZERO
                    for (i = 0; i < 4; i = i + 1)
                        for (j = 0; j < 4; j = j + 1)
                            acc[16*wid + 4*i + j] <= 32'd0;
                end
                default: begin
                end
            endcase
        end
    end

endmodule
