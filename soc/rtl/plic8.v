module plic8 (
  input clk,
  input rst,
  input we,
  input re,
  input [31:0] addr,
  input [31:0] wdata,
  input s1,
  input s2,
  input s3,
  input s4,
  input s5,
  output reg [31:0] rdata,
  output meip0,
  output meip1,
  output meip2,
  output meip3,
  output seip0,
  output seip1,
  output seip2,
  output seip3
);

  localparam [31:0] OFF_PRIO1 = 32'd1;
  localparam [31:0] OFF_PRIO2 = 32'd2;
  localparam [31:0] OFF_PRIO3 = 32'd3;
  localparam [31:0] OFF_PRIO4 = 32'd4;
  localparam [31:0] OFF_PRIO5 = 32'd5;
  localparam [31:0] OFF_PENDING = 32'h0400;
  localparam [31:0] OFF_ENABLE_BASE = 32'h0800;
  localparam [31:0] OFF_ENABLE_STRIDE = 32'h20;
  localparam [31:0] OFF_THRESHOLD_BASE = 32'h80000;
  localparam [31:0] OFF_THRESHOLD_STRIDE = 32'h400;
  localparam [31:0] OFF_CLAIM_BASE = 32'h80001;
  localparam [31:0] OFF_CLAIM_STRIDE = 32'h400;

  wire [31:0] off = {8'd0, addr[25:2]};

  reg [2:0] prio [1:5];
  reg [5:0] enable [0:7];
  reg [2:0] threshold [0:7];
  reg in_service [1:5];
  reg [2:0] claim [0:7];

  // Combinational claim computation
  always @* begin
    integer c, s;
    reg [2:0] max_prio;
    reg [2:0] max_src;
    for (c = 0; c < 8; c = c + 1) begin
      max_prio = 3'd0;
      max_src = 3'd0;
      for (s = 1; s <= 5; s = s + 1) begin
        if ( (s==1 ? s1 : (s==2 ? s2 : (s==3 ? s3 : (s==4 ? s4 : s5)))) &&
             !in_service[s] &&
             enable[c][s] &&
             (prio[s] > threshold[c]) ) begin
          if (prio[s] > max_prio || (prio[s] == max_prio && s < max_src)) begin
            max_prio = prio[s];
            max_src = s[2:0];
          end
        end
      end
      claim[c] = max_src;
    end
  end

  // Combinational read data
  always @* begin
    rdata = 32'd0;
    if (off >= OFF_PRIO1 && off <= OFF_PRIO5) begin
      rdata = {29'd0, prio[off]};
    end else if (off == OFF_PENDING) begin
      rdata = {26'd0, (s5 & ~in_service[5]), (s4 & ~in_service[4]), (s3 & ~in_service[3]),
               (s2 & ~in_service[2]), (s1 & ~in_service[1]), 1'b0};
    end else begin
      integer c;
      for (c = 0; c < 8; c = c + 1) begin
        if (off == OFF_ENABLE_BASE + c * OFF_ENABLE_STRIDE) begin
          rdata = {26'd0, enable[c][5:1], 1'b0};
        end else if (off == OFF_THRESHOLD_BASE + c * OFF_THRESHOLD_STRIDE) begin
          rdata = {29'd0, threshold[c]};
        end else if (off == OFF_CLAIM_BASE + c * OFF_CLAIM_STRIDE) begin
          rdata = {29'd0, claim[c]};
        end
      end
    end
  end

  // Sequential state updates
  always @(posedge clk) begin
    if (rst) begin
      integer i;
      for (i = 1; i <= 5; i = i + 1) begin
        prio[i] <= 3'd0;
        in_service[i] <= 1'b0;
      end
      for (i = 0; i < 8; i = i + 1) begin
        enable[i] <= 6'd0;
        threshold[i] <= 3'd0;
      end
    end else begin
      if (we) begin
        if (off >= OFF_PRIO1 && off <= OFF_PRIO5) begin
          prio[off] <= wdata[2:0];
        end else begin
          integer c;
          for (c = 0; c < 8; c = c + 1) begin
            if (off == OFF_ENABLE_BASE + c * OFF_ENABLE_STRIDE) begin
              enable[c] <= {wdata[5:1], 1'b0};
            end else if (off == OFF_THRESHOLD_BASE + c * OFF_THRESHOLD_STRIDE) begin
              threshold[c] <= wdata[2:0];
            end else if (off == OFF_CLAIM_BASE + c * OFF_CLAIM_STRIDE) begin
              if (wdata >= 32'd1 && wdata <= 32'd5) begin
                in_service[wdata] <= 1'b0;
              end
            end
          end
        end
      end else if (re) begin
        integer c;
        for (c = 0; c < 8; c = c + 1) begin
          if (off == OFF_CLAIM_BASE + c * OFF_CLAIM_STRIDE) begin
            if (claim[c] != 3'd0) begin
              in_service[claim[c]] <= 1'b1;
            end
          end
        end
      end
    end
  end

  assign meip0 = (claim[0] != 3'd0);
  assign meip1 = (claim[2] != 3'd0);
  assign meip2 = (claim[4] != 3'd0);
  assign meip3 = (claim[6] != 3'd0);
  assign seip0 = (claim[1] != 3'd0);
  assign seip1 = (claim[3] != 3'd0);
  assign seip2 = (claim[5] != 3'd0);
  assign seip3 = (claim[7] != 3'd0);

endmodule
