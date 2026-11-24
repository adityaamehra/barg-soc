module tex_addr (
    input  wire [127:0] a,
    input  wire [127:0] b,
    input  wire [2:0]   tex_mode,
    output wire [7:0]   ta00,
    output wire [7:0]   ta01,
    output wire [7:0]   ta02,
    output wire [7:0]   ta03,
    output wire [7:0]   ta10,
    output wire [7:0]   ta11,
    output wire [7:0]   ta12,
    output wire [7:0]   ta13,
    output wire [7:0]   ta20,
    output wire [7:0]   ta21,
    output wire [7:0]   ta22,
    output wire [7:0]   ta23,
    output wire [7:0]   ta30,
    output wire [7:0]   ta31,
    output wire [7:0]   ta32,
    output wire [7:0]   ta33
);
    wire [7:0] iu0, iv0, iu1, iv1, iu2, iv2, iu3, iv3;
    assign iu0 = a[15:8];  assign iv0 = b[15:8];
    assign iu1 = a[47:40]; assign iv1 = b[47:40];
    assign iu2 = a[79:72]; assign iv2 = b[79:72];
    assign iu3 = a[111:104]; assign iv3 = b[111:104];

    // wrap on u axis: repeat (tex_mode[1]==0) -> c mod 32; clamp -> min(c,31)
    // wrap on v axis: repeat (tex_mode[2]==0) -> c mod 32; clamp -> min(c,31)
    // c is 9 bits (0..256)
    function [4:0] wrap;
        input [8:0] c;
        input rep;
        reg [8:0] cc;
        begin
            cc = c;
            if (rep)
                wrap = cc[4:0];
            else
                wrap = (cc > 9'd31) ? 5'd31 : cc[4:0];
        end
    endfunction

    wire [4:0] x0_0, x1_0, y0_0, y1_0;
    wire [4:0] x0_1, x1_1, y0_1, y1_1;
    wire [4:0] x0_2, x1_2, y0_2, y1_2;
    wire [4:0] x0_3, x1_3, y0_3, y1_3;

    assign x0_0 = wrap({1'b0, iu0}, ~tex_mode[1]); assign x1_0 = wrap({1'b0, iu0} + 9'd1, ~tex_mode[1]);
    assign y0_0 = wrap({1'b0, iv0}, ~tex_mode[2]); assign y1_0 = wrap({1'b0, iv0} + 9'd1, ~tex_mode[2]);
    assign x0_1 = wrap({1'b0, iu1}, ~tex_mode[1]); assign x1_1 = wrap({1'b0, iu1} + 9'd1, ~tex_mode[1]);
    assign y0_1 = wrap({1'b0, iv1}, ~tex_mode[2]); assign y1_1 = wrap({1'b0, iv1} + 9'd1, ~tex_mode[2]);
    assign x0_2 = wrap({1'b0, iu2}, ~tex_mode[1]); assign x1_2 = wrap({1'b0, iu2} + 9'd1, ~tex_mode[1]);
    assign y0_2 = wrap({1'b0, iv2}, ~tex_mode[2]); assign y1_2 = wrap({1'b0, iv2} + 9'd1, ~tex_mode[2]);
    assign x0_3 = wrap({1'b0, iu3}, ~tex_mode[1]); assign x1_3 = wrap({1'b0, iu3} + 9'd1, ~tex_mode[1]);
    assign y0_3 = wrap({1'b0, iv3}, ~tex_mode[2]); assign y1_3 = wrap({1'b0, iv3} + 9'd1, ~tex_mode[2]);

    // bank k = py*2 + px: xk = (x0 mod 2 == px) ? x0 : x1, yk likewise
    // ta = (yk>>1)*16 + (xk>>1) = {yk[4:1], xk[4:1]}
    wire [4:0] xa0_0 = x0_0[0] ? x1_0 : x0_0; // px=0: use x0 only if x0 even
    wire [4:0] xa1_0 = x0_0[0] ? x0_0 : x1_0; // px=1
    wire [4:0] ya0_0 = y0_0[0] ? y1_0 : y0_0; // py=0
    wire [4:0] ya1_0 = y0_0[0] ? y0_0 : y1_0; // py=1
    assign ta00 = {ya0_0[4:1], xa0_0[4:1]}; // py=0, px=0
    assign ta01 = {ya0_0[4:1], xa1_0[4:1]}; // py=0, px=1
    assign ta02 = {ya1_0[4:1], xa0_0[4:1]}; // py=1, px=0
    assign ta03 = {ya1_0[4:1], xa1_0[4:1]}; // py=1, px=1

    wire [4:0] xa0_1 = x0_1[0] ? x1_1 : x0_1;
    wire [4:0] xa1_1 = x0_1[0] ? x0_1 : x1_1;
    wire [4:0] ya0_1 = y0_1[0] ? y1_1 : y0_1;
    wire [4:0] ya1_1 = y0_1[0] ? y0_1 : y1_1;
    assign ta10 = {ya0_1[4:1], xa0_1[4:1]};
    assign ta11 = {ya0_1[4:1], xa1_1[4:1]};
    assign ta12 = {ya1_1[4:1], xa0_1[4:1]};
    assign ta13 = {ya1_1[4:1], xa1_1[4:1]};

    wire [4:0] xa0_2 = x0_2[0] ? x1_2 : x0_2;
    wire [4:0] xa1_2 = x0_2[0] ? x0_2 : x1_2;
    wire [4:0] ya0_2 = y0_2[0] ? y1_2 : y0_2;
    wire [4:0] ya1_2 = y0_2[0] ? y0_2 : y1_2;
    assign ta20 = {ya0_2[4:1], xa0_2[4:1]};
    assign ta21 = {ya0_2[4:1], xa1_2[4:1]};
    assign ta22 = {ya1_2[4:1], xa0_2[4:1]};
    assign ta23 = {ya1_2[4:1], xa1_2[4:1]};

    wire [4:0] xa0_3 = x0_3[0] ? x1_3 : x0_3;
    wire [4:0] xa1_3 = x0_3[0] ? x0_3 : x1_3;
    wire [4:0] ya0_3 = y0_3[0] ? y1_3 : y0_3;
    wire [4:0] ya1_3 = y0_3[0] ? y0_3 : y1_3;
    assign ta30 = {ya0_3[4:1], xa0_3[4:1]};
    assign ta31 = {ya0_3[4:1], xa1_3[4:1]};
    assign ta32 = {ya1_3[4:1], xa0_3[4:1]};
    assign ta33 = {ya1_3[4:1], xa1_3[4:1]};
endmodule
