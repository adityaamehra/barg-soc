// barg_fpu: the arithmetic of the RISC-V F and D extensions for RV32 (single and double precision), one operation at a time. Written by rule from the
// RISC-V specification (no model writes it); verified against an exact reference (tb/fpu_ref.py) over directed and random vectors with every rounding mode.
//
// Interface. A request is taken at the clock edge where start is 1 while busy is 0: op, dbl, rm, a, b, c and ia are captured. done is 1 for one cycle when the
// result is ready (1 cycle after start for most operations, about 60 cycles for divide and square root); fres, ires, flags and wr_f then stay valid until the
// next start. busy is 1 while an operation is running.
//   op (5 bits)  0 FADD 1 FSUB 2 FMUL 3 FDIV 4 FSQRT 5 FMADD 6 FMSUB 7 FNMSUB 8 FNMADD 9 FSGNJ 10 FSGNJN 11 FSGNJX 12 FMIN 13 FMAX 14 FEQ 15 FLT 16 FLE
//                17 FCLASS 18 FCVT.W 19 FCVT.WU 20 FCVT.FW 21 FCVT.FWU 22 FCVT.S.D 23 FCVT.D.S 24 FMV.X.W 25 FMV.W.X
//   dbl          1 for double, 0 for single: the format of the operands (and of the result of an FP result), also of fcvt's FP side; ignored by 22, 23, 24, 25
//   rm (3 bits)  0 RNE 1 RTZ 2 RDN 3 RUP 4 RMM (the core resolves a dynamic rounding mode before the start; 5 to 7 act like RNE)
//   a, b, c      64-bit FP register values (a single is NaN-boxed: upper 32 bits all ones; an improperly boxed single reads as the canonical NaN)
//   ia           the integer operand of FCVT.FW, FCVT.FWU, FMV.W.X
//   fres         the FP result (a single comes NaN-boxed); ires the integer result; wr_f is 1 when the result is the FP one, 0 when it is the integer one
//   flags        {NV, DZ, OF, UF, NX} of this operation (not accumulated)
// Tininess is detected after rounding. The canonical NaN is 0x7FC00000 (single) or 0x7FF8000000000000 (double). A synchronous active-high reset aborts any operation.

// ---------------------------------------------------------------------------------------------------------------------------------- unpack
module barg_fpu_unpack (
  input  wire [63:0]        x,
  input  wire               dbl,
  output reg                s,
  output reg  [1:0]         kind,     // 0 zero, 1 finite nonzero, 2 infinity, 3 NaN
  output reg                snan,
  output reg  signed [14:0] e,        // exponent of the leading one (unbiased), subnormals normalised
  output reg  [52:0]        sig       // bit 52 is the leading one (0 when kind is not 1)
);
  reg [31:0] w;
  reg [51:0] frac52;
  reg [22:0] f23;
  integer lz, i;
  always @* begin
    s = 1'b0; kind = 2'd0; snan = 1'b0; e = 15'sd0; sig = 53'd0; lz = 0; w = 32'd0; frac52 = 52'd0; f23 = 23'd0;
    if (dbl) begin
      s = x[63];
      frac52 = x[51:0];
      if (x[62:52] == 11'h7FF) begin
        if (frac52 == 52'd0) kind = 2'd2; else begin kind = 2'd3; snan = ~frac52[51]; end
      end else if (x[62:52] == 11'd0) begin
        if (frac52 != 52'd0) begin
          kind = 2'd1;
          for (i = 51; i >= 0; i = i - 1) if (frac52[i] == 1'b0 && lz == 51 - i) lz = lz + 1;
          sig = {1'b0, frac52} << (lz + 1);
          e = -15'sd1023 - lz;
        end
      end else begin
        kind = 2'd1; sig = {1'b1, frac52}; e = $signed({4'b0000, x[62:52]}) - 15'sd1023;
      end
    end else begin
      w = (x[63:32] == 32'hFFFFFFFF) ? x[31:0] : 32'h7FC00000;
      s = w[31];
      f23 = w[22:0];
      frac52 = {f23, 29'd0};
      if (w[30:23] == 8'hFF) begin
        if (f23 == 23'd0) kind = 2'd2; else begin kind = 2'd3; snan = ~f23[22]; end
      end else if (w[30:23] == 8'd0) begin
        if (f23 != 23'd0) begin
          kind = 2'd1;
          for (i = 51; i >= 0; i = i - 1) if (frac52[i] == 1'b0 && lz == 51 - i) lz = lz + 1;
          sig = {1'b0, frac52} << (lz + 1);
          e = -15'sd127 - lz;
        end
      end else begin
        kind = 2'd1; sig = {1'b1, f23, 29'd0}; e = $signed({7'b0000000, w[30:23]}) - 15'sd127;
      end
    end
  end
endmodule

// ---------------------------------------------------------------------------------------------------------------------------------- round and pack
module barg_fpu_round (
  input  wire               s,
  input  wire [1:0]         kind,     // 0 zero, 1 finite nonzero (e, sig, stky), 2 infinity, 3 NaN
  input  wire               nv_in,
  input  wire signed [14:0] e,        // exponent of the leading one
  input  wire [63:0]        sig,      // bit 63 is the leading one
  input  wire               stky,     // nonzero bits below sig
  input  wire [2:0]         rm,
  input  wire               dbl,
  output reg  [63:0]        res,
  output reg  [4:0]         flags
);
  function inc_fn(input [2:0] r, input sg, input lsb, input g, input rest);
    case (r)
      3'd1: inc_fn = 1'b0;
      3'd2: inc_fn = sg & (g | rest);
      3'd3: inc_fn = ~sg & (g | rest);
      3'd4: inc_fn = g;
      default: inc_fn = g & (rest | lsb);
    endcase
  endfunction
  integer emin, emax, bias, ee, ee2, sh, eu, ebiased;
  reg [191:0] tmp;
  reg [63:0] sigs;
  reg stk1, g, rest, inexact, inc, carry, normalized, ovf, tiny;
  reg [52:0] m, m2, mu;
  reg [53:0] msum, musum;
  reg gu, restu, incu, carryu;
  always @* begin
    emin = dbl ? -1022 : -126; emax = dbl ? 1023 : 127; bias = dbl ? 1023 : 127;
    res = 64'd0; flags = 5'd0;
    tmp = 192'd0; sigs = 64'd0; stk1 = 1'b0; g = 1'b0; rest = 1'b0; inexact = 1'b0; inc = 1'b0; carry = 1'b0; normalized = 1'b0; ovf = 1'b0; tiny = 1'b0;
    m = 53'd0; m2 = 53'd0; mu = 53'd0; msum = 54'd0; musum = 54'd0; gu = 1'b0; restu = 1'b0; incu = 1'b0; carryu = 1'b0;
    ee = 0; ee2 = 0; sh = 0; eu = 0; ebiased = 0;
    if (kind == 2'd3) begin
      res = dbl ? 64'h7FF8000000000000 : 64'hFFFFFFFF7FC00000; flags = {nv_in, 4'd0};
    end else if (kind == 2'd2) begin
      res = dbl ? {s, 11'h7FF, 52'd0} : {32'hFFFFFFFF, s, 8'hFF, 23'd0}; flags = {nv_in, 4'd0};
    end else if (kind == 2'd0) begin
      res = dbl ? {s, 63'd0} : {32'hFFFFFFFF, s, 31'd0}; flags = {nv_in, 4'd0};
    end else begin
      ee = e;
      sh = (ee < emin) ? (emin - ee) : 0;
      if (sh > 128) sh = 128;
      tmp = {sig, 128'd0} >> sh;
      sigs = tmp[191:128];
      stk1 = stky | (|tmp[127:0]);
      if (ee < emin) ee = emin;
      if (dbl) begin m = sigs[63:11]; g = sigs[10]; rest = (|sigs[9:0]) | stk1; end
      else begin m = {29'd0, sigs[63:40]}; g = sigs[39]; rest = (|sigs[38:0]) | stk1; end
      inexact = g | rest;
      inc = inc_fn(rm, s, m[0], g, rest);
      msum = {1'b0, m} + {53'd0, inc};
      carry = dbl ? msum[53] : msum[24];
      if (carry) begin m2 = dbl ? 53'h10000000000000 : 53'h00000000800000; ee2 = ee + 1; end
      else begin m2 = dbl ? msum[52:0] : {29'd0, msum[23:0]}; ee2 = ee; end
      normalized = dbl ? m2[52] : m2[23];
      ovf = normalized && (ee2 > emax);
      // tininess after rounding: round the unshifted significand with an unbounded exponent
      if (dbl) begin mu = sig[63:11]; gu = sig[10]; restu = (|sig[9:0]) | stky; end
      else begin mu = {29'd0, sig[63:40]}; gu = sig[39]; restu = (|sig[38:0]) | stky; end
      incu = inc_fn(rm, s, mu[0], gu, restu);
      musum = {1'b0, mu} + {53'd0, incu};
      carryu = dbl ? musum[53] : musum[24];
      eu = e + (carryu ? 1 : 0);
      tiny = (eu < emin);
      ebiased = normalized ? (ee2 + bias) : 0;
      if (ovf) begin
        flags = 5'b00101;
        if (rm == 3'd1 || (rm == 3'd2 && !s) || (rm == 3'd3 && s)) res = dbl ? {s, 11'h7FE, 52'hFFFFFFFFFFFFF} : {32'hFFFFFFFF, s, 8'hFE, 23'h7FFFFF};
        else res = dbl ? {s, 11'h7FF, 52'd0} : {32'hFFFFFFFF, s, 8'hFF, 23'd0};
      end else begin
        flags = {nv_in, 1'b0, 1'b0, (tiny & inexact), inexact};
        res = dbl ? {s, ebiased[10:0], m2[51:0]} : {32'hFFFFFFFF, s, ebiased[7:0], m2[22:0]};
      end
    end
  end
endmodule

// ---------------------------------------------------------------------------------------------------------------------------------- fused multiply-add (exact, before rounding)
module barg_fpu_fma (
  input  wire               sa, input wire [1:0] ka, input wire na, input wire signed [14:0] ea, input wire [52:0] siga,
  input  wire               sb, input wire [1:0] kb, input wire nb, input wire signed [14:0] eb, input wire [52:0] sigb,
  input  wire               sc0, input wire [1:0] kc, input wire nc, input wire signed [14:0] ec, input wire [52:0] sigc,
  input  wire               has_c, input wire neg_prod, input wire neg_c, input wire [2:0] rm,
  output reg  [1:0]         kind,
  output reg                s,
  output reg  signed [14:0] e,
  output reg  [63:0]        sig,
  output reg                stky,
  output reg                nv
);
  wire sp = sa ^ sb ^ neg_prod;
  wire sc = sc0 ^ neg_c;
  wire anynan = (ka == 2'd3) | (kb == 2'd3) | (has_c & (kc == 2'd3));
  wire snan_any = na | nb | (has_c & nc);
  wire inf_zero = ((ka == 2'd2) & (kb == 2'd0)) | ((ka == 2'd0) & (kb == 2'd2));
  wire pzero = (ka == 2'd0) | (kb == 2'd0);
  wire czero = ~has_c | (kc == 2'd0);
  wire [105:0] p = siga * sigb;
  reg [105:0] pn;
  reg signed [15:0] ep, d, E;
  reg [108:0] pw, cw, lg, sm, smt;
  reg [236:0] tmp;
  reg sl, ss, sticky_al;
  reg [109:0] r;
  integer dcap, lz, i;
  reg [109:0] rn;
  reg pbig;
  always @* begin
    kind = 2'd0; s = 1'b0; e = 15'sd0; sig = 64'd0; stky = 1'b0; nv = snan_any | inf_zero;
    pn = 106'd0; ep = 16'sd0; d = 16'sd0; E = 16'sd0; pw = 109'd0; cw = 109'd0; lg = 109'd0; sm = 109'd0; smt = 109'd0; tmp = 237'd0;
    sl = 1'b0; ss = 1'b0; sticky_al = 1'b0; r = 110'd0; dcap = 0; lz = 0; rn = 110'd0; pbig = 1'b0;
    if (anynan | inf_zero) begin
      kind = 2'd3;
    end else if ((ka == 2'd2) | (kb == 2'd2)) begin
      if (has_c & (kc == 2'd2) & (sc != sp)) begin kind = 2'd3; nv = 1'b1; end
      else begin kind = 2'd2; s = sp; end
    end else if (has_c & (kc == 2'd2)) begin
      kind = 2'd2; s = sc;
    end else if (pzero & czero) begin
      kind = 2'd0;
      if (!has_c) s = sp; else s = (sp == sc) ? sp : (rm == 3'd2);
    end else if (pzero) begin
      kind = 2'd1; s = sc; e = ec; sig = {sigc, 11'd0}; stky = 1'b0;
    end else if (czero) begin
      kind = 2'd1; s = sp;
      if (p[105]) begin e = ea + eb + 15'sd1; sig = p[105:42]; stky = |p[41:0]; end
      else begin e = ea + eb; sig = p[104:41]; stky = |p[40:0]; end
    end else begin
      pbig = p[105];
      pn = pbig ? p : (p << 1);
      ep = $signed({ea[14], ea}) + $signed({eb[14], eb}) + (pbig ? 16'sd1 : 16'sd0);
      pw = {pn, 3'b000};
      cw = {sigc, 53'd0, 3'b000};
      d = ep - $signed({ec[14], ec});
      if (d > 16'sd0 || (d == 16'sd0 && pw >= cw)) begin       // the product is the larger operand
        E = ep; lg = pw; sl = sp; ss = sc;
        dcap = (d > 16'sd128) ? 128 : d;
        tmp = {cw, 128'd0} >> dcap;
      end else begin
        E = $signed({ec[14], ec}); lg = cw; sl = sc; ss = sp;
        dcap = (-d > 16'sd128) ? 128 : -d;
        tmp = {pw, 128'd0} >> dcap;
      end
      smt = tmp[236:128];
      sticky_al = |tmp[127:0];
      if (sl == ss) r = {1'b0, lg} + {1'b0, smt};
      else r = {1'b0, lg} - {1'b0, smt} - {109'd0, sticky_al};
      stky = sticky_al;
      if (r == 110'd0 && !sticky_al) begin
        kind = 2'd0; s = (rm == 3'd2);                          // exact cancellation
      end else begin
        kind = 2'd1; s = sl;
        for (i = 109; i >= 0; i = i - 1) if (r[i] == 1'b0 && lz == 109 - i) lz = lz + 1;
        rn = r << lz;
        sig = rn[109:46];
        stky = sticky_al | (|rn[45:0]);
        e = E + 16'sd1 - lz;
      end
    end
  end
endmodule

// ---------------------------------------------------------------------------------------------------------------------------------- the unit
module barg_fpu (
  input  wire        clk,
  input  wire        rst,
  input  wire        start,
  input  wire [4:0]  op,
  input  wire        dbl,
  input  wire [2:0]  rm,
  input  wire [63:0] a,
  input  wire [63:0] b,
  input  wire [63:0] c,
  input  wire [31:0] ia,
  output wire        busy,
  output wire        done,
  output wire [63:0] fres,
  output wire [31:0] ires,
  output wire [4:0]  flags,
  output wire        wr_f
);
  localparam [1:0] S_IDLE = 2'd0, S_RUN = 2'd1;
  reg [1:0] state;
  reg done_q;
  reg [4:0] op_q; reg dbl_q; reg [2:0] rm_q; reg [63:0] a_q, b_q, c_q; reg [31:0] ia_q;
  reg [6:0] cnt;
  assign busy = (state == S_RUN);
  assign done = done_q;

  wire is_div = (op_q == 5'd3);
  wire is_sqrt = (op_q == 5'd4);

  // ------------------------------------------------------------------ operands
  wire sa_, sb_, sc_, sac; wire [1:0] ka, kb, kc, kac; wire na, nb, nc, nac; wire signed [14:0] ea, eb, ec, eac; wire [52:0] siga, sigb, sigc, sigac;
  wire cvt_dbl = (op_q == 5'd22);
  barg_fpu_unpack ua (.x(a_q), .dbl(dbl_q), .s(sa_), .kind(ka), .snan(na), .e(ea), .sig(siga));
  barg_fpu_unpack ub (.x(b_q), .dbl(dbl_q), .s(sb_), .kind(kb), .snan(nb), .e(eb), .sig(sigb));
  barg_fpu_unpack uc (.x(c_q), .dbl(dbl_q), .s(sc_), .kind(kc), .snan(nc), .e(ec), .sig(sigc));
  barg_fpu_unpack uac (.x(a_q), .dbl(cvt_dbl), .s(sac), .kind(kac), .snan(nac), .e(eac), .sig(sigac));   // the source of FCVT.S.D / FCVT.D.S

  // ------------------------------------------------------------------ fused multiply-add family (add, subtract, multiply, fused ops)
  wire is_addsub = (op_q == 5'd0) | (op_q == 5'd1);
  wire is_mul = (op_q == 5'd2);
  wire [52:0] one_sig = 53'h10000000000000;
  wire fsa = sa_;
  wire [1:0] fkb = is_addsub ? 2'd1 : kb;
  wire fsb = is_addsub ? 1'b0 : sb_;
  wire signed [14:0] feb = is_addsub ? 15'sd0 : eb;
  wire [52:0] fsigb = is_addsub ? one_sig : sigb;
  wire fnb = is_addsub ? 1'b0 : nb;
  // addend: b for add/subtract, c for the fused operations
  wire fsc = is_addsub ? sb_ : sc_;
  wire [1:0] fkc = is_addsub ? kb : kc;
  wire fnc = is_addsub ? nb : nc;
  wire signed [14:0] fec = is_addsub ? eb : ec;
  wire [52:0] fsigc = is_addsub ? sigb : sigc;
  wire has_c = ~is_mul;
  wire neg_prod = (op_q == 5'd7) | (op_q == 5'd8);
  wire neg_c = (op_q == 5'd1) | (op_q == 5'd6) | (op_q == 5'd8);
  wire [1:0] f_kind; wire f_s; wire signed [14:0] f_e; wire [63:0] f_sig; wire f_stky, f_nv;
  barg_fpu_fma fma (.sa(fsa), .ka(ka), .na(na), .ea(ea), .siga(siga), .sb(fsb), .kb(fkb), .nb(fnb), .eb(feb), .sigb(fsigb),
                    .sc0(fsc), .kc(fkc), .nc(fnc), .ec(fec), .sigc(fsigc), .has_c(has_c), .neg_prod(neg_prod), .neg_c(neg_c), .rm(rm_q),
                    .kind(f_kind), .s(f_s), .e(f_e), .sig(f_sig), .stky(f_stky), .nv(f_nv));

  // ------------------------------------------------------------------ divide and square root (iterative)
  reg [55:0] q_q;              // quotient / root
  reg [59:0] rem_q;
  reg [111:0] n_q;             // radicand of the square root, shifted left two bits per step
  reg signed [15:0] ediv_q;    // the result's exponent before normalisation
  reg [1:0] dkind_q; reg ds_q; reg dnv_q, ddz_q;
  wire div_special_nan = (ka == 2'd3) | (kb == 2'd3);
  wire signed [15:0] ediff = $signed({ea[14], ea}) - $signed({eb[14], eb});
  wire e_odd = ea[0];
  wire signed [15:0] mprime = $signed({ea[14], ea}) - (e_odd ? 16'sd53 : 16'sd52);

  // ------------------------------------------------------------------ rounding input selection
  reg [1:0] r_kind; reg r_s, r_nv; reg signed [14:0] r_e; reg [63:0] r_sig; reg r_stky; reg r_dbl; reg [4:0] r_extra_flags;
  reg [31:0] mag; reg [63:0] m64; integer lzi, j;
  always @* begin
    r_kind = 2'd0; r_s = 1'b0; r_nv = 1'b0; r_e = 15'sd0; r_sig = 64'd0; r_stky = 1'b0; r_dbl = dbl_q; r_extra_flags = 5'd0;
    mag = 32'd0; m64 = 64'd0; lzi = 0;
    case (op_q)
      5'd0, 5'd1, 5'd2, 5'd5, 5'd6, 5'd7, 5'd8: begin
        r_kind = f_kind; r_s = f_s; r_nv = f_nv; r_e = f_e; r_sig = f_sig; r_stky = f_stky;
      end
      5'd3, 5'd4: begin
        r_kind = dkind_q; r_s = ds_q; r_nv = dnv_q; r_e = ediv_q[14:0];
        if (is_div) begin
          if (q_q[55]) begin r_sig = {q_q, 8'd0}; end
          else begin r_sig = {q_q[54:0], 9'd0}; r_e = ediv_q[14:0] - 15'sd1; end
        end else r_sig = {q_q, 8'd0};
        r_stky = (rem_q != 60'd0);
        r_extra_flags = {1'b0, ddz_q, 3'd0};
      end
      5'd20, 5'd21: begin
        if (op_q == 5'd21) begin mag = ia_q; r_s = 1'b0; end
        else begin r_s = ia_q[31]; mag = ia_q[31] ? (~ia_q + 32'd1) : ia_q; end
        m64 = {32'd0, mag};
        for (j = 63; j >= 0; j = j - 1) if (m64[j] == 1'b0 && lzi == 63 - j) lzi = lzi + 1;
        if (mag == 32'd0) begin r_kind = 2'd0; r_s = 1'b0; end
        else begin r_kind = 2'd1; r_sig = m64 << lzi; r_e = 63 - lzi; end
      end
      5'd22, 5'd23: begin
        r_dbl = (op_q == 5'd23);
        r_kind = kac; r_s = sac; r_nv = nac; r_e = eac; r_sig = {sigac, 11'd0}; r_stky = 1'b0;
      end
      default: ;
    endcase
  end
  wire [63:0] rnd_res; wire [4:0] rnd_flags;
  barg_fpu_round rnd (.s(r_s), .kind(r_kind), .nv_in(r_nv), .e(r_e), .sig(r_sig), .stky(r_stky), .rm(rm_q), .dbl(r_dbl), .res(rnd_res), .flags(rnd_flags));

  // ------------------------------------------------------------------ comparisons, min/max, sign injection, class, moves, FP to integer
  // value ordering of two operands that are not NaN
  reg lt, eq;
  reg mlt, meq;
  always @* begin
    // magnitude compare of a and b (infinity > finite > zero; finite by exponent then significand)
    meq = 1'b0; mlt = 1'b0;
    if (ka == 2'd0 && kb == 2'd0) meq = 1'b1;
    else if (ka == 2'd2 && kb == 2'd2) meq = 1'b1;
    else if (ka == 2'd1 && kb == 2'd1) begin
      if (ea == eb && siga == sigb) meq = 1'b1;
      else mlt = (ea < eb) || (ea == eb && siga < sigb);
    end else mlt = (ka == 2'd0) || (kb == 2'd2);          // zero < finite < infinity
    eq = 1'b0; lt = 1'b0;
    if (ka == 2'd0 && kb == 2'd0) eq = 1'b1;
    else if (sa_ != sb_) lt = sa_;                          // the negative one is smaller
    else if (meq) eq = 1'b1;
    else lt = sa_ ? ~mlt : mlt;
  end
  wire anynan_ab = (ka == 2'd3) | (kb == 2'd3);
  wire a_boxed = &a_q[63:32];
  wire b_boxed = &b_q[63:32];
  wire [31:0] a32 = a_boxed ? a_q[31:0] : 32'h7FC00000;
  wire [31:0] b32 = b_boxed ? b_q[31:0] : 32'h7FC00000;
  wire [63:0] la = dbl_q ? a_q : {32'hFFFFFFFF, a32};
  wire [63:0] lb = dbl_q ? b_q : {32'hFFFFFFFF, b32};
  wire [63:0] cnan = dbl_q ? 64'h7FF8000000000000 : 64'hFFFFFFFF7FC00000;
  reg [63:0] mm_res; reg [4:0] mm_flags;
  reg pick_a;
  always @* begin
    mm_res = la; mm_flags = {(na | nb), 4'd0}; pick_a = 1'b1;
    if (ka == 2'd3 && kb == 2'd3) mm_res = cnan;
    else if (ka == 2'd3) mm_res = lb;
    else if (kb == 2'd3) mm_res = la;
    else begin
      if (eq) begin
        if (ka == 2'd0) pick_a = (op_q == 5'd12) ? sa_ : ~sa_;     // zeros of different sign: -0 is the smaller
        else pick_a = 1'b1;
      end else pick_a = (op_q == 5'd12) ? lt : ~lt;
      mm_res = pick_a ? la : lb;
    end
  end
  // sign injection
  reg [63:0] sj_res; reg sgn;
  always @* begin
    sgn = 1'b0; sj_res = 64'd0;
    if (dbl_q) begin
      sgn = (op_q == 5'd9) ? b_q[63] : (op_q == 5'd10) ? ~b_q[63] : (a_q[63] ^ b_q[63]);
      sj_res = {sgn, a_q[62:0]};
    end else begin
      sgn = (op_q == 5'd9) ? b32[31] : (op_q == 5'd10) ? ~b32[31] : (a32[31] ^ b32[31]);
      sj_res = {32'hFFFFFFFF, sgn, a32[30:0]};
    end
  end
  // class
  reg [31:0] cls;
  wire subn = dbl_q ? (ea < -15'sd1022) : (ea < -15'sd126);
  always @* begin
    cls = 32'd0;
    case (ka)
      2'd3: cls = na ? 32'h100 : 32'h200;
      2'd2: cls = sa_ ? 32'h001 : 32'h080;
      2'd0: cls = sa_ ? 32'h008 : 32'h010;
      default: cls = sa_ ? (subn ? 32'h004 : 32'h002) : (subn ? 32'h020 : 32'h040);
    endcase
  end
  // FP to integer
  reg [31:0] f2i_res; reg [4:0] f2i_flags;
  reg [127:0] t; reg [63:0] v64; reg [34:0] n, n2; reg gg, rr, ii, inc_i; integer sh2;
  reg unsig;
  function inc_fi(input [2:0] r, input sg, input lsb, input g, input rest);
    case (r)
      3'd1: inc_fi = 1'b0;
      3'd2: inc_fi = sg & (g | rest);
      3'd3: inc_fi = ~sg & (g | rest);
      3'd4: inc_fi = g;
      default: inc_fi = g & (rest | lsb);
    endcase
  endfunction
  always @* begin
    unsig = (op_q == 5'd19);
    f2i_res = 32'd0; f2i_flags = 5'd0; t = 128'd0; v64 = 64'd0; n = 35'd0; n2 = 35'd0; gg = 1'b0; rr = 1'b0; ii = 1'b0; inc_i = 1'b0; sh2 = 0;
    if (ka == 2'd3 || (ka == 2'd2 && !sa_)) begin f2i_res = unsig ? 32'hFFFFFFFF : 32'h7FFFFFFF; f2i_flags = 5'b10000; end
    else if (ka == 2'd2) begin f2i_res = unsig ? 32'd0 : 32'h80000000; f2i_flags = 5'b10000; end
    else if (ka == 2'd0) begin f2i_res = 32'd0; end
    else begin
      v64 = {siga, 11'd0};
      if (ea > 15'sd33) begin
        f2i_res = sa_ ? (unsig ? 32'd0 : 32'h80000000) : (unsig ? 32'hFFFFFFFF : 32'h7FFFFFFF); f2i_flags = 5'b10000;
      end else begin
        if (ea >= 15'sd0) begin
          sh2 = 63 - ea;
          t = {v64, 64'd0} >> sh2;
          n = t[98:64];
          gg = t[63]; rr = |t[62:0];
        end else if (ea == -15'sd1) begin
          n = 35'd0; gg = 1'b1; rr = |siga[51:0];
        end else begin
          n = 35'd0; gg = 1'b0; rr = 1'b1;
        end
        ii = gg | rr;
        inc_i = inc_fi(rm_q, sa_, n[0], gg, rr);
        n2 = n + {34'd0, inc_i};
        if (sa_) begin
          if (unsig) begin
            if (n2 == 35'd0) begin f2i_res = 32'd0; f2i_flags = {4'd0, ii}; end
            else begin f2i_res = 32'd0; f2i_flags = 5'b10000; end
          end else begin
            if (n2 > 35'h80000000) begin f2i_res = 32'h80000000; f2i_flags = 5'b10000; end
            else begin f2i_res = (~n2[31:0]) + 32'd1; f2i_flags = {4'd0, ii}; end
          end
        end else begin
          if (unsig) begin
            if (n2 > 35'hFFFFFFFF) begin f2i_res = 32'hFFFFFFFF; f2i_flags = 5'b10000; end
            else begin f2i_res = n2[31:0]; f2i_flags = {4'd0, ii}; end
          end else begin
            if (n2 > 35'h7FFFFFFF) begin f2i_res = 32'h7FFFFFFF; f2i_flags = 5'b10000; end
            else begin f2i_res = n2[31:0]; f2i_flags = {4'd0, ii}; end
          end
        end
      end
    end
  end

  // ------------------------------------------------------------------ result selection
  reg [63:0] fres_r; reg [31:0] ires_r; reg [4:0] flags_r; reg wr_f_r;
  always @* begin
    fres_r = 64'd0; ires_r = 32'd0; flags_r = 5'd0; wr_f_r = 1'b1;
    case (op_q)
      5'd0, 5'd1, 5'd2, 5'd3, 5'd4, 5'd5, 5'd6, 5'd7, 5'd8, 5'd20, 5'd21, 5'd22, 5'd23: begin
        fres_r = rnd_res; flags_r = rnd_flags | r_extra_flags;
      end
      5'd9, 5'd10, 5'd11: fres_r = sj_res;
      5'd12, 5'd13: begin fres_r = mm_res; flags_r = mm_flags; end
      5'd14, 5'd15, 5'd16: begin
        wr_f_r = 1'b0;
        if (op_q == 5'd14) flags_r = {(na | nb), 4'd0}; else flags_r = {anynan_ab, 4'd0};
        if (!anynan_ab) ires_r = {31'd0, (op_q == 5'd14) ? eq : (op_q == 5'd15) ? lt : (lt | eq)};
      end
      5'd17: begin wr_f_r = 1'b0; ires_r = cls; end
      5'd18, 5'd19: begin wr_f_r = 1'b0; ires_r = f2i_res; flags_r = f2i_flags; end
      5'd24: begin wr_f_r = 1'b0; ires_r = a_q[31:0]; end
      5'd25: fres_r = {32'hFFFFFFFF, ia_q};
      default: ;
    endcase
  end
  assign fres = fres_r;
  assign ires = ires_r;
  assign flags = flags_r;
  assign wr_f = wr_f_r;

  // ------------------------------------------------------------------ sequencing
  always @(posedge clk) begin
    if (rst) begin
      state <= S_IDLE; done_q <= 1'b0; cnt <= 7'd0; op_q <= 5'd0; dbl_q <= 1'b0; rm_q <= 3'd0; a_q <= 64'd0; b_q <= 64'd0; c_q <= 64'd0; ia_q <= 32'd0;
      q_q <= 56'd0; rem_q <= 58'd0; n_q <= 112'd0; ediv_q <= 16'sd0; dkind_q <= 2'd0; ds_q <= 1'b0; dnv_q <= 1'b0; ddz_q <= 1'b0;
    end else begin
      done_q <= 1'b0;
      case (state)
        S_IDLE: if (start) begin
          op_q <= op; dbl_q <= dbl; rm_q <= (rm > 3'd4) ? 3'd0 : rm; a_q <= a; b_q <= b; c_q <= c; ia_q <= ia; cnt <= 7'd0; state <= S_RUN;
        end
        S_RUN: begin
          if (is_div || is_sqrt) begin
            if (cnt == 7'd0) begin                                    // initialise from the captured operands
              ds_q <= is_div ? (sa_ ^ sb_) : sa_;
              dnv_q <= 1'b0; ddz_q <= 1'b0; dkind_q <= 2'd1; q_q <= 56'd0;
              rem_q <= {7'd0, siga};
              ediv_q <= ediff;
              n_q <= 112'd0;
              if (is_div) begin
                if (div_special_nan) begin dkind_q <= 2'd3; dnv_q <= na | nb; end
                else if (((ka == 2'd2) && (kb == 2'd2)) || ((ka == 2'd0) && (kb == 2'd0))) begin dkind_q <= 2'd3; dnv_q <= 1'b1; end
                else if (ka == 2'd2) dkind_q <= 2'd2;
                else if (kb == 2'd2) dkind_q <= 2'd0;
                else if (kb == 2'd0) begin dkind_q <= 2'd2; ddz_q <= 1'b1; end
                else if (ka == 2'd0) dkind_q <= 2'd0;
                else dkind_q <= 2'd1;
                rem_q <= {7'd0, siga};
              end else begin
                if (ka == 2'd3) begin dkind_q <= 2'd3; dnv_q <= na; end
                else if (ka == 2'd0) dkind_q <= 2'd0;
                else if (sa_) begin dkind_q <= 2'd3; dnv_q <= 1'b1; end
                else if (ka == 2'd2) dkind_q <= 2'd2;
                else dkind_q <= 2'd1;
                ediv_q <= (mprime >>> 1) + 16'sd26;
                n_q <= (e_odd ? {58'd0, siga, 1'b0} : {59'd0, siga}) << 58;
                rem_q <= 60'd0;
              end
              cnt <= 7'd1;
            end else begin
              if (is_div) begin
                // one quotient bit per cycle, 56 bits
                if (rem_q >= {7'd0, sigb}) begin q_q <= {q_q[54:0], 1'b1}; rem_q <= (rem_q - {7'd0, sigb}) << 1; end
                else begin q_q <= {q_q[54:0], 1'b0}; rem_q <= rem_q << 1; end
                // the shift of the final remainder only matters for "nonzero", which it keeps
                if (cnt == 7'd56) begin
                  done_q <= 1'b1; state <= S_IDLE; cnt <= 7'd0;
                end else cnt <= cnt + 7'd1;
              end else begin
                // square root: two radicand bits per cycle, 56 root bits
                if ({rem_q[57:0], n_q[111:110]} >= {2'b00, q_q, 2'b01}) begin
                  rem_q <= {rem_q[57:0], n_q[111:110]} - {2'b00, q_q, 2'b01};
                  q_q <= {q_q[54:0], 1'b1};
                end else begin
                  rem_q <= {rem_q[57:0], n_q[111:110]};
                  q_q <= {q_q[54:0], 1'b0};
                end
                n_q <= n_q << 2;
                if (cnt == 7'd56) begin done_q <= 1'b1; state <= S_IDLE; cnt <= 7'd0; end
                else cnt <= cnt + 7'd1;
              end
            end
          end else begin
            done_q <= 1'b1; state <= S_IDLE;
          end
        end
        default: state <= S_IDLE;
      endcase
    end
  end
endmodule
