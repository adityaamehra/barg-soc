module tlb32(
    input  clk,
    input  rst,
    input  flush,
    input  fill,
    input  [19:0] fill_vpn,
    input  [21:0] fill_ppn,
    input  fill_mega,
    input  [7:0]  fill_flags,
    input  [31:0] va,
    output hit,
    output [19:0] ppa,
    output [7:0]  flags
);
    // Entry fields
    reg valid [0:31];
    reg [19:0] vpn   [0:31];
    reg [21:0] ppn   [0:31];
    reg        mega  [0:31];
    reg [7:0]  fbits [0:31];

    // Pointer to next fill entry
    reg [4:0] ptr;

    // Combinational lookup
    integer i;
    reg found;
    reg [19:0] found_ppa;
    reg [7:0]  found_flags;

    always @* begin
        found = 1'b0;
        found_ppa = 20'd0;
        found_flags = 8'd0;
        for (i = 0; i < 32; i = i + 1) begin
            if (!found && valid[i]) begin
                if (mega[i]) begin
                    if (vpn[i][19:10] == va[31:22]) begin
                        found = 1'b1;
                        found_ppa = {ppn[i][19:10], va[21:12]};
                        found_flags = fbits[i];
                    end
                end else begin
                    if (vpn[i] == va[31:12]) begin
                        found = 1'b1;
                        found_ppa = ppn[i][19:0];
                        found_flags = fbits[i];
                    end
                end
            end
        end
    end

    assign hit   = found;
    assign ppa   = found_ppa;
    assign flags = found_flags;

    // Sequential logic for entries and ptr
    always @(posedge clk) begin
        if (rst || flush) begin
            integer j;
            for (j = 0; j < 32; j = j + 1) begin
                valid[j] <= 1'b0;
                vpn[j]   <= 20'd0;
                ppn[j]   <= 22'd0;
                mega[j]  <= 1'b0;
                fbits[j] <= 8'd0;
            end
            ptr <= 5'd0;
        end else if (fill) begin
            valid[ptr] <= 1'b1;
            vpn[ptr]   <= fill_vpn;
            ppn[ptr]   <= fill_ppn;
            mega[ptr]  <= fill_mega;
            fbits[ptr] <= fill_flags;
            ptr <= ptr + 5'd1;
        end
    end

endmodule
