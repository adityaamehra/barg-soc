// TMDS (DVI 1.0 / HDMI) encoder for two consecutive pixels per clock of one colour channel: returns 20 bits, the first pixel's 10-bit symbol in [9:0]
// (it is sent first: the GTH sends bit 0 first), the second in [19:10]. The running disparity `cnt` is chained through both pixels inside one clock.
module tmds_enc2 (
  input  wire        clk,
  input  wire        de,            // 1 in the active picture: pixel data; 0 in blanking: the control code of c1c0
  input  wire [1:0]  c,             // c1 c0 (hsync/vsync on the blue channel, 0 on the others)
  input  wire [7:0]  d0, d1,        // the two pixels' 8-bit colour values
  output reg  [19:0] q
);
  function [8:0] stage1(input [7:0] d);
    integer i; reg [3:0] n1; reg xnor_sel; reg [8:0] m;
    begin
      n1 = 0; for (i = 0; i < 8; i = i + 1) n1 = n1 + d[i];
      xnor_sel = (n1 > 4) || (n1 == 4 && d[0] == 1'b0);
      m[0] = d[0];
      for (i = 1; i < 8; i = i + 1) m[i] = xnor_sel ? ~(m[i-1] ^ d[i]) : (m[i-1] ^ d[i]);
      m[8] = ~xnor_sel;
      stage1 = m;
    end
  endfunction
  // one symbol and the new disparity from the 9-bit word m and the running disparity cnt (signed, 5 bits is enough)
  function [14:0] stage2(input [8:0] m, input signed [4:0] cnt);
    integer i; reg [3:0] n1, n0; reg signed [4:0] diff; reg [9:0] o; reg signed [4:0] nc;
    begin
      n1 = 0; for (i = 0; i < 8; i = i + 1) n1 = n1 + m[i];
      n0 = 8 - n1;
      diff = $signed({1'b0, n1}) - $signed({1'b0, n0});      // n1 - n0
      if (cnt == 0 || n1 == n0) begin
        o[9] = ~m[8]; o[8] = m[8]; o[7:0] = m[8] ? m[7:0] : ~m[7:0];
        nc = (m[8] == 1'b0) ? cnt - diff : cnt + diff;
      end else if ((cnt > 0 && n1 > n0) || (cnt < 0 && n0 > n1)) begin
        o[9] = 1'b1; o[8] = m[8]; o[7:0] = ~m[7:0];
        nc = cnt + (m[8] ? 5'sd2 : 5'sd0) - diff;
      end else begin
        o[9] = 1'b0; o[8] = m[8]; o[7:0] = m[7:0];
        nc = cnt - (m[8] ? 5'sd0 : 5'sd2) + diff;
      end
      stage2 = {nc, o};
    end
  endfunction
  function [9:0] ctl_code(input [1:0] cc);
    case (cc)
      2'b00: ctl_code = 10'b1101010100;
      2'b01: ctl_code = 10'b0010101011;
      2'b10: ctl_code = 10'b0101010100;
      default: ctl_code = 10'b1010101011;
    endcase
  endfunction
  reg signed [4:0] cnt = 0;
  wire [8:0] m0 = stage1(d0), m1 = stage1(d1);
  wire [14:0] s0 = stage2(m0, cnt);
  wire [14:0] s1 = stage2(m1, $signed(s0[14:10]));
  always @(posedge clk) begin
    if (de) begin
      q   <= {s1[9:0], s0[9:0]};
      cnt <= $signed(s1[14:10]);
    end else begin
      q   <= {ctl_code(c), ctl_code(c)};
      cnt <= 0;
    end
  end
endmodule
