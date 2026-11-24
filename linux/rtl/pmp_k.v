module pmp_k (
    input  wire        store,      // 1-bit input
    output wire [1:0]  kind_f,     // 2-bit output
    output wire [1:0]  kind_d,     // 2-bit output
    output wire [1:0]  kind_l,     // 2-bit output
    output wire [1:0]  priv_s,     // 2-bit output
    output wire        one         // 1-bit output
);

// Constant assignments
assign kind_f = 2'b00;          // always 00
assign kind_l = 2'b01;          // always 01
assign priv_s = 2'b01;          // always 01
assign one    = 1'b1;           // always 1

// kind_d depends on store
assign kind_d = store ? 2'b10 : 2'b01;

endmodule
