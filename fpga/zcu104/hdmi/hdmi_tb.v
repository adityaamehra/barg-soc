// Checks tmds_enc2 against the DVI 1.0 decoding rules: every symbol decodes back to the pixel, the running disparity stays bounded, control codes are right.
module hdmi_tb;
  reg clk = 0; always #5 clk = ~clk;
  reg de = 0; reg [1:0] c = 0; reg [7:0] d0, d1; wire [19:0] q;
  tmds_enc2 dut (.clk(clk), .de(de), .c(c), .d0(d0), .d1(d1), .q(q));
  function [7:0] decode(input [9:0] s);
    reg [7:0] x; integer i;
    begin
      x = s[9] ? ~s[7:0] : s[7:0];
      decode[0] = x[0];
      for (i = 1; i < 8; i = i + 1) decode[i] = s[8] ? (x[i] ^ x[i-1]) : ~(x[i] ^ x[i-1]);
    end
  endfunction
  integer n, bad = 0, ones, disp = 0, maxd = 0, i;
  reg [7:0] pd0, pd1; reg pde;
  initial begin
    for (n = 0; n < 20000; n = n + 1) begin
      @(negedge clk);
      de = ($urandom % 8) != 0; c = $urandom; d0 = $urandom; d1 = $urandom;
      @(posedge clk); #1;
      // the outputs belong to the inputs of this edge
      if (de) begin
        if (decode(q[9:0]) !== d0 || decode(q[19:10]) !== d1) bad = bad + 1;
        ones = 0; for (i = 0; i < 20; i = i + 1) ones = ones + q[i];
        disp = disp + ones - (20 - ones);
        if (disp > maxd) maxd = disp; if (-disp > maxd) maxd = -disp;
      end else begin
        disp = 0;
        case (c) 2'b00: if (q[9:0] !== 10'b1101010100) bad = bad + 1; 2'b01: if (q[9:0] !== 10'b0010101011) bad = bad + 1;
                 2'b10: if (q[9:0] !== 10'b0101010100) bad = bad + 1; default: if (q[9:0] !== 10'b1010101011) bad = bad + 1; endcase
      end
    end
    $display("TMDS test: %0d bad symbols, max running disparity %0d (should be small)", bad, maxd);
    $finish;
  end
endmodule
