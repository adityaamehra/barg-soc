module plic4 (
  input clk,
  input rst,
  input we,
  input re,
  input [31:0] addr,
  input [31:0] wdata,
  input s1,
  input s2,
  input s3,
  output reg [31:0] rdata,
  output meip0,
  output meip1,
  output meip2,
  output meip3
);

  localparam [31:0] OFF_PRIO1 = 32'd1;
  localparam [31:0] OFF_PRIO2 = 32'd2;
  localparam [31:0] OFF_PRIO3 = 32'd3;
  localparam [31:0] OFF_PENDING = 32'h0400;
  localparam [31:0] OFF_ENABLE_BASE = 32'h0800;
  localparam [31:0] OFF_ENABLE_STRIDE = 32'h20;
  localparam [31:0] OFF_THRESHOLD_BASE = 32'h80000;
  localparam [31:0] OFF_THRESHOLD_STRIDE = 32'h400;
  localparam [31:0] OFF_CLAIM_BASE = 32'h80001;
  localparam [31:0] OFF_CLAIM_STRIDE = 32'h400;

  wire [31:0] off = {8'd0, addr[25:2]};

  reg [2:0] prio [1:3];
  reg [3:0] enable [0:3];
  reg [2:0] threshold [0:3];
  reg in_service [1:3];
  reg [1:0] claim [0:3];

  // Combinational claim computation
  always @* begin
    integer c, s;
    reg [2:0] max_prio;
    reg [1:0] max_src;
    for (c = 0; c < 4; c = c + 1) begin
      max_prio = 3'd0;
      max_src = 2'd0;
      for (s = 1; s <= 3; s = s + 1) begin
        if ( (s==1 ? s1 : (s==2 ? s2 : s3)) &&
             !in_service[s] &&
             enable[c][s] &&
             (prio[s] > threshold[c]) ) begin
          if (prio[s] > max_prio || (prio[s] == max_prio && s < max_src)) begin
            max_prio = prio[s];
            max_src = s[1:0];
          end
        end
      end
      claim[c] = max_src;
    end
  end

  // Combinational read data
  always @* begin
    rdata = 32'd0;
    if (off >= OFF_PRIO1 && off <= OFF_PRIO3) begin
      rdata = {29'd0, prio[off]};
    end else if (off == OFF_PENDING) begin
      rdata = {28'd0, (s3 & ~in_service[3]), (s2 & ~in_service[2]), (s1 & ~in_service[1]), 1'b0};
    end else begin
      integer c;
      for (c = 0; c < 4; c = c + 1) begin
        if (off == OFF_ENABLE_BASE + c * OFF_ENABLE_STRIDE) begin
          rdata = {28'd0, enable[c][3:1], 1'b0};
        end else if (off == OFF_THRESHOLD_BASE + c * OFF_THRESHOLD_STRIDE) begin
          rdata = {29'd0, threshold[c]};
        end else if (off == OFF_CLAIM_BASE + c * OFF_CLAIM_STRIDE) begin
          rdata = {30'd0, claim[c]};
        end
      end
    end
  end

  // Sequential state updates
  always @(posedge clk) begin
    if (rst) begin
      integer i;
      for (i = 1; i <= 3; i = i + 1) begin
        prio[i] <= 3'd0;
        in_service[i] <= 1'b0;
      end
      for (i = 0; i < 4; i = i + 1) begin
        enable[i] <= 4'd0;
        threshold[i] <= 3'd0;
      end
    end else begin
      if (we) begin
        if (off >= OFF_PRIO1 && off <= OFF_PRIO3) begin
          prio[off] <= wdata[2:0];
        end else begin
          integer c;
          for (c = 0; c < 4; c = c + 1) begin
            if (off == OFF_ENABLE_BASE + c * OFF_ENABLE_STRIDE) begin
              enable[c] <= {wdata[3:1], 1'b0};
            end else if (off == OFF_THRESHOLD_BASE + c * OFF_THRESHOLD_STRIDE) begin
              threshold[c] <= wdata[2:0];
            end else if (off == OFF_CLAIM_BASE + c * OFF_CLAIM_STRIDE) begin
              if (wdata >= 32'd1 && wdata <= 32'd3) begin
                in_service[wdata] <= 1'b0;
              end
            end
          end
        end
      end else if (re) begin
        integer c;
        for (c = 0; c < 4; c = c + 1) begin
          if (off == OFF_CLAIM_BASE + c * OFF_CLAIM_STRIDE) begin
            if (claim[c] != 2'd0) begin
              in_service[claim[c]] <= 1'b1;
            end
          end
        end
      end
    end
  end

  assign meip0 = (claim[0] != 2'd0);
  assign meip1 = (claim[1] != 2'd0);
  assign meip2 = (claim[2] != 2'd0);
  assign meip3 = (claim[3] != 2'd0);

endmodule
