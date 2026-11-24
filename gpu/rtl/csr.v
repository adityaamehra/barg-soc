module csr (
    input  wire [11:0] csr_addr,
    input  wire        valid,
    input  wire [2:0]  unit,
    input  wire [1:0]  wid,
    input  wire [3:0]  tmask,
    input  wire [31:0] karg,
    input  wire [47:0] cycle,
    output wire [127:0] y,
    output wire        err
);
    reg [31:0] lane_val;
    reg [127:0] y_r;
    integer l;

    always @* begin
        y_r = 128'd0;
        for (l = 0; l < 4; l = l + 1) begin
            case (csr_addr)
                12'hCC0: lane_val = l[31:0];
                12'hCC1: lane_val = {30'd0, wid};
                12'hCC2: lane_val = 32'd0;
                12'hCC3: lane_val = {28'd0, tmask};
                12'hCC4: lane_val = {28'd0, wid} * 32'd4 + l[31:0];
                12'hCC5: lane_val = karg;
                12'hFC0: lane_val = 32'd4;
                12'hFC1: lane_val = 32'd4;
                12'hFC2: lane_val = 32'd1;
                12'hC00: lane_val = cycle[31:0];
                12'hC02: lane_val = cycle[31:0];
                12'hC80: lane_val = {16'd0, cycle[47:32]};
                12'hC82: lane_val = {16'd0, cycle[47:32]};
                default: lane_val = 32'd0;
            endcase
            y_r[l*32 +: 32] = lane_val;
        end
    end

    assign y = y_r;
    assign err = valid && (unit == 3'b110) &&
                 !((csr_addr == 12'hCC0) || (csr_addr == 12'hCC1) ||
                   (csr_addr == 12'hCC2) || (csr_addr == 12'hCC3) ||
                   (csr_addr == 12'hCC4) || (csr_addr == 12'hCC5) ||
                   (csr_addr == 12'hFC0) || (csr_addr == 12'hFC1) ||
                   (csr_addr == 12'hFC2) || (csr_addr == 12'hC00) ||
                   (csr_addr == 12'hC02) || (csr_addr == 12'hC80) ||
                   (csr_addr == 12'hC82));
endmodule
