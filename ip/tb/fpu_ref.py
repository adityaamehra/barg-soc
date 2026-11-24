"""Exact reference model of the RISC-V F and D extensions' arithmetic (RV32), for testing barg_fpu. Pure Python with exact rational and integer arithmetic,
so it does not depend on the host's floating point. Written from the RISC-V specification (unprivileged ISA, chapters F and D).

Operations (op codes of barg_fpu):
  0 FADD 1 FSUB 2 FMUL 3 FDIV 4 FSQRT 5 FMADD 6 FMSUB 7 FNMSUB 8 FNMADD 9 FSGNJ 10 FSGNJN 11 FSGNJX 12 FMIN 13 FMAX 14 FEQ 15 FLT 16 FLE
  17 FCLASS 18 FCVT.W 19 FCVT.WU 20 FCVT.FW (int to float) 21 FCVT.FWU 22 FCVT.S.D 23 FCVT.D.S 24 FMV.X.W 25 FMV.W.X
Rounding modes: 0 RNE, 1 RTZ, 2 RDN, 3 RUP, 4 RMM. Flags: bit 4 NV, 3 DZ, 2 OF, 1 UF, 0 NX.
A single is NaN-boxed in the low half of a 64-bit register (upper 32 bits all ones); a register that is not properly boxed reads as the canonical NaN.
Tininess is detected after rounding (RISC-V).  run(op, dbl, rm, a, b, c, ia) -> (fres, ires, flags, wr_f)
"""
from fractions import Fraction
from math import isqrt

NV, DZ, OF, UF, NX = 16, 8, 4, 2, 1
FMT = {0: dict(p=24, emin=-126, emax=127, ebits=8, bias=127), 1: dict(p=53, emin=-1022, emax=1023, ebits=11, bias=1023)}
CNAN = {0: 0xFFFFFFFF7FC00000, 1: 0x7FF8000000000000}
M64 = (1 << 64) - 1


def unpack(x, dbl):
    """-> (kind, sign, value as Fraction (>= 0), snan). kind: 'zero' 'fin' 'inf' 'nan'."""
    if dbl:
        s, ef, fr = x >> 63 & 1, x >> 52 & 0x7FF, x & ((1 << 52) - 1)
        if ef == 0x7FF:
            return ("inf", s, None, False) if fr == 0 else ("nan", s, None, not fr >> 51 & 1)
        if ef == 0:
            return ("zero", s, Fraction(0), False) if fr == 0 else ("fin", s, Fraction(fr) * Fraction(1, 1 << 1074), False)
        return ("fin", s, Fraction((1 << 52) | fr) * (Fraction(2) ** (ef - 1075)), False)
    w = x & 0xFFFFFFFF if (x >> 32) == 0xFFFFFFFF else 0x7FC00000
    s, ef, fr = w >> 31 & 1, w >> 23 & 0xFF, w & 0x7FFFFF
    if ef == 0xFF:
        return ("inf", s, None, False) if fr == 0 else ("nan", s, None, not fr >> 22 & 1)
    if ef == 0:
        return ("zero", s, Fraction(0), False) if fr == 0 else ("fin", s, Fraction(fr) * Fraction(1, 1 << 149), False)
    return ("fin", s, Fraction((1 << 23) | fr) * (Fraction(2) ** (ef - 150)), False)


def pack(dbl, s, ef, fr):
    if dbl:
        return s << 63 | ef << 52 | fr
    return 0xFFFFFFFF00000000 | s << 31 | ef << 23 | fr


def inf_bits(dbl, s):
    return pack(dbl, s, 0x7FF if dbl else 0xFF, 0)


def maxfin_bits(dbl, s):
    return pack(dbl, s, 0x7FE if dbl else 0xFE, (1 << 52) - 1 if dbl else (1 << 23) - 1)


def _inc(rm, s, lsb, g, rest):
    inexact = g or rest
    if rm == 0:
        return g and (rest or lsb)
    if rm == 1:
        return False
    if rm == 2:
        return bool(s) and inexact
    if rm == 3:
        return not s and inexact
    return bool(g)


def round_value(dbl, s, x, rm):
    """Round the positive exact value x (Fraction, > 0) with sign s to the format; -> (bits, flags)."""
    f = FMT[dbl]
    p, emin, emax = f["p"], f["emin"], f["emax"]
    e = x.numerator.bit_length() - x.denominator.bit_length()       # floor(log2 x) is e or e - 1
    if x < Fraction(2) ** e:
        e -= 1

    def rnd(quantum_exp):
        q = x / (Fraction(2) ** quantum_exp)
        n = q.numerator // q.denominator
        rem = q - n
        g = rem >= Fraction(1, 2)
        rest = rem != 0 and (rem - (Fraction(1, 2) if g else 0)) != 0
        inexact = rem != 0
        if _inc(rm, s, n & 1, g, rest):
            n += 1
        return n, inexact

    flags = 0
    n, inexact = rnd(max(e, emin) - (p - 1))
    if inexact:
        flags |= NX
    # tininess after rounding: round once more with an unbounded exponent
    nu, _ = rnd(e - (p - 1))
    eu = e + 1 if nu >= 1 << p else e
    if eu < emin and inexact:
        flags |= UF
    qe = max(e, emin) - (p - 1)
    if n == 1 << p:                                                  # rounding carried into a new power of two: renormalise
        n >>= 1
        qe += 1
    value = Fraction(n) * Fraction(2) ** qe
    if value >= Fraction(2) ** (emax + 1):
        flags |= OF | NX
        if rm == 0 or rm == 4 or (rm == 2 and s) or (rm == 3 and not s):
            return inf_bits(dbl, s), flags
        return maxfin_bits(dbl, s), flags
    if n == 0:
        return pack(dbl, s, 0, 0), flags
    ee = n.bit_length() - 1 + qe                                     # exponent of the leading one
    if ee < emin:                                                    # subnormal
        return pack(dbl, s, 0, n), flags
    return pack(dbl, s, ee + f["bias"], n - (1 << (p - 1))), flags


def zero_bits(dbl, s):
    return pack(dbl, s, 0, 0)


def to_fr(kind_s):
    kind, s, v, _ = kind_s
    return -v if s else v


def fma_like(dbl, rm, ua, ub, uc, neg_prod, neg_c):
    """A*B (+ C): exact. uc None means no addend (fmul). -> (bits, flags)."""
    ka, sa, va, na = ua
    kb, sb, vb, nb = ub
    kc, sc, vc, nc = uc if uc is not None else ("zero", 0, Fraction(0), False)
    snan = na or nb or (nc if uc is not None else False)
    inf_zero = (ka == "inf" and kb == "zero") or (ka == "zero" and kb == "inf")
    anynan = ka == "nan" or kb == "nan" or (uc is not None and kc == "nan")
    sp = sa ^ sb ^ neg_prod
    sc2 = sc ^ neg_c
    flags = NV if (snan or inf_zero) else 0
    if anynan or inf_zero:
        return CNAN[dbl], flags
    c_present = uc is not None
    if ka == "inf" or kb == "inf":
        if c_present and kc == "inf" and sc2 != sp:
            return CNAN[dbl], NV
        return inf_bits(dbl, sp), 0
    if c_present and kc == "inf":
        return inf_bits(dbl, sc2), 0
    prod = (-1 if sp else 1) * va * vb
    add = (-1 if sc2 else 1) * vc if c_present else Fraction(0)
    pzero = ka == "zero" or kb == "zero"
    czero = (not c_present) or kc == "zero"
    total = prod + add
    if total == 0:
        if pzero and czero:                                           # both operands are zero
            if not c_present:
                return zero_bits(dbl, sp), 0
            return zero_bits(dbl, sp if sp == sc2 else (1 if rm == 2 else 0)), 0
        return zero_bits(dbl, 1 if rm == 2 else 0), 0                 # exact cancellation
    s = 1 if total < 0 else 0
    return round_value(dbl, s, abs(total), rm)


def fdiv(dbl, rm, ua, ub):
    ka, sa, va, na = ua
    kb, sb, vb, nb = ub
    s = sa ^ sb
    if ka == "nan" or kb == "nan":
        return CNAN[dbl], NV if (na or nb) else 0
    if (ka == "inf" and kb == "inf") or (ka == "zero" and kb == "zero"):
        return CNAN[dbl], NV
    if ka == "inf":
        return inf_bits(dbl, s), 0
    if kb == "inf":
        return zero_bits(dbl, s), 0
    if kb == "zero":
        return inf_bits(dbl, s), DZ
    if ka == "zero":
        return zero_bits(dbl, s), 0
    return round_value(dbl, s, va / vb, rm)


def fsqrt(dbl, rm, ua):
    ka, sa, va, na = ua
    if ka == "nan":
        return CNAN[dbl], NV if na else 0
    if ka == "zero":
        return zero_bits(dbl, sa), 0
    if sa:
        return CNAN[dbl], NV
    if ka == "inf":
        return inf_bits(dbl, 0), 0
    # correctly rounded square root of va (exact rational): use integers with a sticky bit
    n, d = va.numerator, va.denominator
    k = 140                                                          # extra bits so the root has well over 64 bits
    r = isqrt(n * d * (1 << (2 * k)))                                # floor(sqrt(n/d) * d * 2^k)
    exact = r * r == n * d * (1 << (2 * k))
    # sqrt(n/d) = sqrt(n*d)/d ; value = (r + frac) / (d * 2^k), frac in [0,1)
    root = Fraction(r, d * (1 << k))
    if not exact:
        root += Fraction(1, 2) * Fraction(1, d * (1 << k))           # inside the interval: any point decides the rounding as the interval is far narrower than an ulp
    return round_value(dbl, 0, root, rm)


def cvt_to_int(dbl, rm, ua, unsigned):
    kind, s, v, _ = ua
    lim_pos = 0xFFFFFFFF if unsigned else 0x7FFFFFFF
    lim_neg = 0 if unsigned else 0x80000000
    if kind == "nan" or (kind == "inf" and not s):
        return lim_pos, NV
    if kind == "inf":
        return lim_neg, NV
    n = v.numerator // v.denominator
    rem = v - n
    g = rem >= Fraction(1, 2)
    rest = rem != 0 and (rem - (Fraction(1, 2) if g else 0)) != 0
    if _inc(rm, s, n & 1, g, rest):
        n += 1
    inexact = rem != 0
    if s:
        if unsigned:
            if n == 0:
                return 0, (NX if inexact else 0)
            return 0, NV
        if n > 0x80000000:
            return 0x80000000, NV
        return (-n) & 0xFFFFFFFF, (NX if inexact else 0)
    if n > lim_pos:
        return lim_pos, NV
    return n, (NX if inexact else 0)


def cvt_from_int(dbl, rm, ia, unsigned):
    if unsigned:
        mag, s = ia & 0xFFFFFFFF, 0
    else:
        v = ia & 0xFFFFFFFF
        s = v >> 31
        mag = (-v) & 0xFFFFFFFF if s else v
        if v == 0x80000000:
            mag = 0x80000000
    if mag == 0:
        return zero_bits(dbl, 0), 0
    return round_value(dbl, s, Fraction(mag), rm)


def fclass(dbl, a):
    kind, s, v, snan = unpack(a, dbl)
    if kind == "nan":
        return 1 << (8 if snan else 9)
    if kind == "inf":
        return 1 << (0 if s else 7)
    if kind == "zero":
        return 1 << (3 if s else 4)
    sub = v < (Fraction(2) ** FMT[dbl]["emin"])
    return 1 << ((2 if sub else 1) if s else (5 if sub else 6))


def _key(u):
    """Order key of a non-NaN operand: (rank, value) with rank -1 for -infinity, 0 for finite (and zero), 1 for +infinity."""
    kind, sg, v, _ = u
    if kind == "inf":
        return (-1 if sg else 1, Fraction(0))
    return (0, -v if sg else v)


def cmp_vals(ua, ub):
    ka, kb = _key(ua), _key(ub)
    return (ka > kb) - (ka < kb)


def run(op, dbl, rm, a, b, c, ia):
    """-> (fres, ires, flags, wr_f). Operands a, b, c are 64-bit register values; ia the integer operand."""
    a, b, c, ia = a & M64, b & M64, c & M64, ia & 0xFFFFFFFF
    if op in (0, 1, 2):
        ua, ub = unpack(a, dbl), unpack(b, dbl)
        if op == 2:
            r = fma_like(dbl, rm, ua, ub, None, 0, 0)
        elif op == 0:
            r = fma_like(dbl, rm, ua, ("fin", 0, Fraction(1), False) if False else unpack(0x3FF0000000000000 if dbl else 0xFFFFFFFF3F800000, dbl), ub, 0, 0)
        else:
            r = fma_like(dbl, rm, ua, unpack(0x3FF0000000000000 if dbl else 0xFFFFFFFF3F800000, dbl), ub, 0, 1)
        return r[0], 0, r[1], 1
    if op in (5, 6, 7, 8):
        ua, ub, uc = unpack(a, dbl), unpack(b, dbl), unpack(c, dbl)
        neg_prod = 1 if op in (7, 8) else 0
        neg_c = 1 if op in (6, 8) else 0
        r = fma_like(dbl, rm, ua, ub, uc, neg_prod, neg_c)
        return r[0], 0, r[1], 1
    if op == 3:
        r = fdiv(dbl, rm, unpack(a, dbl), unpack(b, dbl))
        return r[0], 0, r[1], 1
    if op == 4:
        r = fsqrt(dbl, rm, unpack(a, dbl))
        return r[0], 0, r[1], 1
    if op in (9, 10, 11):
        if dbl:
            sa, sb = a >> 63 & 1, b >> 63 & 1
            sa_bits = a & ((1 << 63) - 1)
            sgn = sb if op == 9 else (1 - sb if op == 10 else sa ^ sb)
            return sgn << 63 | sa_bits, 0, 0, 1
        ra = a & 0xFFFFFFFF if (a >> 32) == 0xFFFFFFFF else 0x7FC00000
        rb = b & 0xFFFFFFFF if (b >> 32) == 0xFFFFFFFF else 0x7FC00000
        sa, sb = ra >> 31, rb >> 31
        sgn = sb if op == 9 else (1 - sb if op == 10 else sa ^ sb)
        return 0xFFFFFFFF00000000 | sgn << 31 | (ra & 0x7FFFFFFF), 0, 0, 1
    if op in (12, 13):
        ua, ub = unpack(a, dbl), unpack(b, dbl)
        flags = NV if (ua[3] or ub[3]) else 0
        if ua[0] == "nan" and ub[0] == "nan":
            return CNAN[dbl], 0, flags, 1
        if ua[0] == "nan":
            return b if dbl else (b if (b >> 32) == 0xFFFFFFFF else CNAN[0]), 0, flags, 1
        if ub[0] == "nan":
            return a if dbl else (a if (a >> 32) == 0xFFFFFFFF else CNAN[0]), 0, flags, 1
        la = a if dbl else (0xFFFFFFFF00000000 | (a & 0xFFFFFFFF))
        lb = b if dbl else (0xFFFFFFFF00000000 | (b & 0xFFFFFFFF))
        ca = cmp_vals(ua, ub)
        if ca == 0:                                                  # equal values: -0 < +0
            sa = ua[1]
            pick_a = (sa == 1) if op == 12 else (sa == 0)
            if ua[0] != "zero":
                pick_a = True
            return (la if pick_a else lb), 0, flags, 1
        pick_a = (ca < 0) if op == 12 else (ca > 0)
        return (la if pick_a else lb), 0, flags, 1
    if op in (14, 15, 16):
        ua, ub = unpack(a, dbl), unpack(b, dbl)
        anynan = ua[0] == "nan" or ub[0] == "nan"
        if op == 14:
            flags = NV if (ua[3] or ub[3]) else 0
        else:
            flags = NV if anynan else 0
        if anynan:
            return 0, 0, flags, 0
        ca = cmp_vals(ua, ub)
        res = {14: ca == 0, 15: ca < 0, 16: ca <= 0}[op]
        return 0, int(res), flags, 0
    if op == 17:
        return 0, fclass(dbl, a), 0, 0
    if op in (18, 19):
        r = cvt_to_int(dbl, rm, unpack(a, dbl), op == 19)
        return 0, r[0], r[1], 0
    if op in (20, 21):
        r = cvt_from_int(dbl, rm, ia, op == 21)
        return r[0], 0, r[1], 1
    if op == 22:                                                      # double to single
        ua = unpack(a, 1)
        if ua[0] == "nan":
            return CNAN[0], 0, NV if ua[3] else 0, 1
        if ua[0] == "inf":
            return inf_bits(0, ua[1]), 0, 0, 1
        if ua[0] == "zero":
            return zero_bits(0, ua[1]), 0, 0, 1
        r = round_value(0, ua[1], ua[2], rm)
        return r[0], 0, r[1], 1
    if op == 23:                                                      # single to double
        ua = unpack(a, 0)
        if ua[0] == "nan":
            return CNAN[1], 0, NV if ua[3] else 0, 1
        if ua[0] == "inf":
            return inf_bits(1, ua[1]), 0, 0, 1
        if ua[0] == "zero":
            return zero_bits(1, ua[1]), 0, 0, 1
        r = round_value(1, ua[1], ua[2], rm)
        return r[0], 0, r[1], 1
    if op == 24:
        return 0, a & 0xFFFFFFFF, 0, 0
    if op == 25:
        return 0xFFFFFFFF00000000 | ia, 0, 0, 1
    raise ValueError(op)
