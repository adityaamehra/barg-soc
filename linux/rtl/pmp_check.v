module pmp_check(
    input  [31:0] pa,
    input  [1:0]  kind,
    input  [1:0]  priv,
    input         en,
    input  [127:0] cfg_all,
    input  [511:0] addr_all,
    output reg    deny
);

    integer i;
    reg [31:0] w;
    reg [31:0] addr_i;
    reg [7:0]  c;
    reg [1:0]  mode;
    reg [31:0] prev;
    reg [31:0] m;
    reg        match_i;
    reg        allow_i;
    reg        locked;
    reg        found;
    reg        matched_allow;
    reg        matched_locked;

    always @* begin
        deny = 1'b0;                 // default
        if (!en) begin
            deny = 1'b0;
        end else begin
    w = {2'b0, pa[31:2]};
    found = 1'b0;
            matched_allow = 1'b0;
            matched_locked = 1'b0;

            for (i = 0; i < 16; i = i + 1) begin
                if (!found) begin
                    c      = cfg_all[8*i +: 8];
                    mode   = c[4:3];
                    addr_i = addr_all[32*i +: 32];
                    prev   = (i == 0) ? 32'd0 : addr_all[32*(i-1) +: 32];

                    // compute match
                    case (mode)
                        2'b01: begin // mode 1
                            match_i = (prev <= w) && (w < addr_i);
                        end
                        2'b10: begin // mode 2
                            match_i = (w == addr_i);
                        end
                        2'b11: begin // mode 3
                            m = addr_i ^ (addr_i + 32'd1);
                            match_i = ((w & ~m) == (addr_i & ~m));
                        end
                        default: match_i = 1'b0; // mode 0 never matches
                    endcase

                    // compute allow
                    case (kind)
                        2'b00: allow_i = c[2];
                        2'b01: allow_i = c[0];
                        default: allow_i = c[1]; // kind 10 or 11
                    endcase

                    locked = c[7];

                    if (match_i) begin
                        found = 1'b1;
                        matched_allow = allow_i;
                        matched_locked = locked;
                    end
                end
            end

            if (found) begin
                deny = ((priv != 2'b11) || matched_locked) && !matched_allow;
            end else begin
                deny = (priv != 2'b11);
            end
        end
    end

endmodule
