module host_if (
    input  wire        clk,
    input  wire        rst,
    input  wire        host_en,
    input  wire        host_we,
    input  wire [31:0] host_addr,
    input  wire [31:0] host_wdata,
    input  wire        busy,
    input  wire        advance,
    input  wire [31:0] x_pc,
    input  wire [1:0]  x_wid,
    input  wire        err_illegal,
    input  wire        err_mem,
    input  wire        err_simt,
    input  wire        err_tensor,
    input  wire        err_csr,
    input  wire [127:0] g_rdata,
    input  wire [127:0] s_rdata,
    output wire [31:0] host_rdata,
    output wire        host_rvalid,
    output wire        running,
    output wire        start,
    output wire [31:0] start_pc,
    output wire [31:0] karg,
    output wire        done,
    output wire        error
);

    reg        running_r;
    reg        done_r;
    reg        error_r;
    reg [31:0] start_pc_r;
    reg [31:0] karg_r;
    reg [31:0] err_pc_r;
    reg [9:0]  err_info_r;
    reg        rvalid_r;
    reg [31:0] raddr_r;

    assign running   = running_r;
    assign done      = done_r;
    assign error     = error_r;
    assign start_pc  = start_pc_r;
    assign karg      = karg_r;
    assign host_rvalid = rvalid_r;

    assign start = host_en & host_we & (host_addr == 32'h3000_0000)
                 & host_wdata[0] & ~running_r;

    // cause priority
    reg [3:0] cause;
    always @* begin
        if (err_illegal)      cause = 4'd1;
        else if (err_mem)     cause = 4'd2;
        else if (err_simt)    cause = 4'd3;
        else if (err_tensor)  cause = 4'd4;
        else if (err_csr)     cause = 4'd5;
        else                  cause = 4'd0;
    end

    wire any_cause = err_illegal | err_mem | err_simt | err_tensor | err_csr;

    wire host_wr = host_en & host_we;
    wire wr_start_pc = host_wr & ~running_r & (host_addr == 32'h3000_0004);
    wire wr_karg     = host_wr & ~running_r & (host_addr == 32'h3000_0008);

    always @(posedge clk) begin
        if (rst) begin
            running_r   <= 1'b0;
            done_r      <= 1'b0;
            error_r     <= 1'b0;
            start_pc_r  <= 32'd0;
            karg_r      <= 32'd0;
            err_pc_r    <= 32'd0;
            err_info_r  <= 10'd0;
            rvalid_r    <= 1'b0;
            raddr_r     <= 32'd0;
        end else begin
            if (wr_start_pc) start_pc_r <= host_wdata;
            if (wr_karg)     karg_r     <= host_wdata;

            if (start) begin
                running_r <= 1'b1;
                done_r    <= 1'b0;
                error_r   <= 1'b0;
            end else if (running_r & advance & any_cause) begin
                running_r  <= 1'b0;
                error_r    <= 1'b1;
                err_pc_r   <= x_pc;
                err_info_r <= {x_wid, 4'b0000, cause};
            end else if (running_r & ~busy) begin
                running_r <= 1'b0;
                done_r    <= 1'b1;
            end

            rvalid_r <= host_en & ~host_we;
            raddr_r  <= host_addr;
        end
    end

    // read data mux (combinational from raddr)
    wire in_g = (raddr_r >= 32'h1000_0000) && (raddr_r <= 32'h1000_1FFF);
    wire in_s = (raddr_r >= 32'h2000_0000) && (raddr_r <= 32'h2000_0FFF);
    wire [1:0] word_sel = raddr_r[3:2];

    reg [31:0] ctrl_rdata;
    always @* begin
        case (raddr_r)
            32'h3000_0000: ctrl_rdata = 32'd0;
            32'h3000_0004: ctrl_rdata = start_pc_r;
            32'h3000_0008: ctrl_rdata = karg_r;
            32'h3000_000C: ctrl_rdata = {29'd0, error_r, done_r, running_r};
            32'h3000_0010: ctrl_rdata = err_pc_r;
            32'h3000_0014: ctrl_rdata = {22'd0, err_info_r};
            default:       ctrl_rdata = 32'd0;
        endcase
    end

    assign host_rdata = in_g ? g_rdata[word_sel*32 +: 32]
                      : in_s ? s_rdata[word_sel*32 +: 32]
                      : ctrl_rdata;

endmodule
