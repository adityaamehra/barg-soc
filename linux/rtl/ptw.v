module ptw (
    input clk,
    input rst,
    input start,
    input [31:0] vaddr,
    input [21:0] satp_ppn,
    input grant,
    input [31:0] rdata,
    input clear,
    input deny,
    output busy,
    output req,
    output [31:0] addr,
    output fill,
    output [19:0] fill_vpn,
    output [21:0] fill_ppn,
    output fill_mega,
    output [7:0] fill_flags,
    output fault,
    output fault_access,
    output [19:0] fault_vpn
);
    localparam [1:0] IDLE = 2'd0;
    localparam [1:0] L1   = 2'd1;
    localparam [1:0] L0   = 2'd2;

    reg [1:0] st;
    reg [33:0] a;
    reg [31:0] va;
    reg fault_r;
    reg facc;
    reg [19:0] fvpn_r;

    wire in_ram;
    wire active;
    wire v_pte;
    wire r_pte;
    wire w_pte;
    wire x_pte;
    wire [21:0] pte_ppn;
    wire valid_leaf;

    assign in_ram = (a[33:26] == 8'b0010_0000);
    assign active = (st == L1) || (st == L0);

    assign v_pte = rdata[0];
    assign r_pte = rdata[1];
    assign w_pte = rdata[2];
    assign x_pte = rdata[3];
    assign pte_ppn = rdata[31:10];

    assign valid_leaf =
        v_pte &&
        !((!r_pte) && w_pte) &&
        (r_pte || x_pte) &&
        !((st == L1) && (pte_ppn[9:0] != 10'd0));

    assign busy = (st != IDLE);
    assign req = active && in_ram;
    assign addr = req ? a[31:0] : 32'd0;

    assign fill = req && grant && valid_leaf;
    assign fill_vpn = fill ? va[31:12] : 20'd0;
    assign fill_ppn = fill ? pte_ppn : 22'd0;
    assign fill_mega = fill && (st == L1);
    assign fill_flags = fill ? rdata[7:0] : 8'd0;

    assign fault = fault_r;
    assign fault_access = facc;
    assign fault_vpn = fvpn_r;

    always @(posedge clk) begin
        if (rst) begin
            st <= IDLE;
            a <= 34'd0;
            va <= 32'd0;
            fault_r <= 1'b0;
            facc <= 1'b0;
            fvpn_r <= 20'd0;
        end else if (clear) begin
            st <= IDLE;
            fault_r <= 1'b0;
        end else begin
            case (st)
                IDLE: begin
                    if (start) begin
                        st <= L1;
                        va <= vaddr;
                        a <= {satp_ppn, 12'd0} + {22'd0, vaddr[31:22], 2'b00};
                        fault_r <= 1'b0;
                    end
                end

                L1, L0: begin
                    if (!in_ram || deny) begin
                        st <= IDLE;
                        fault_r <= 1'b1;
                        facc <= 1'b1;
                        fvpn_r <= va[31:12];
                    end else if (grant) begin
                        if (!v_pte || ((!r_pte) && w_pte)) begin
                            st <= IDLE;
                            fault_r <= 1'b1;
                            facc <= 1'b0;
                            fvpn_r <= va[31:12];
                        end else if (r_pte || x_pte) begin
                            if ((st == L1) && (pte_ppn[9:0] != 10'd0)) begin
                                st <= IDLE;
                                fault_r <= 1'b1;
                                facc <= 1'b0;
                                fvpn_r <= va[31:12];
                            end else begin
                                st <= IDLE;
                            end
                        end else begin
                            if ((st == L0) || rdata[7] || rdata[6] || rdata[4]) begin
                                st <= IDLE;
                                fault_r <= 1'b1;
                                facc <= 1'b0;
                                fvpn_r <= va[31:12];
                            end else begin
                                st <= L0;
                                a <= {pte_ppn, 12'd0} + {22'd0, va[21:12], 2'b00};
                            end
                        end
                    end
                end

                default: begin
                    st <= IDLE;
                end
            endcase
        end
    end
endmodule
