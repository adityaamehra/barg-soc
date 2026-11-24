"""Test vectors for barg_fpu from the exact reference model (tb/fpu_ref.py): one line per operation,
   op dbl rm a b c ia | fres ires flags wr_f   (all hexadecimal)
python3 gen_fpu_vectors.py <out file> [--n N] [--seed S] [--ops 0,1,...] [--quick]
Operands mix special values (zeros, infinities, NaNs of both kinds, subnormals, the largest and smallest normals, powers of two, values near integer
boundaries), neighbouring values (one unit in the last place away) and random bit patterns, with exponents close together so that cancellation happens."""
import random, struct, sys
sys.path.insert(0, __import__("os").path.dirname(__file__) or ".")
import fpu_ref as R

args = sys.argv[1:]
opt = lambda k, d=None: args[args.index(k) + 1] if k in args else d  # noqa: E731
out = args[0]
N = int(opt("--n", 400))
rng = random.Random(int(opt("--seed", 1)))
ops = [int(x) for x in opt("--ops", ",".join(map(str, range(26)))).split(",")]
M64 = (1 << 64) - 1


def special(dbl):
    if dbl:
        vals = [0, 1 << 63, 0x3FF0000000000000, 0xBFF0000000000000, 0x4000000000000000, 0x3FE0000000000000, 0x7FF0000000000000, 0xFFF0000000000000,
                0x7FF8000000000000, 0x7FF4000000000000, 0xFFF8000000000001, 0x0000000000000001, 0x000FFFFFFFFFFFFF, 0x0010000000000000, 0x7FEFFFFFFFFFFFFF,
                0xFFEFFFFFFFFFFFFF, 0x4330000000000000, 0x433FFFFFFFFFFFFF, 0x41E0000000000000, 0xC1E0000000000000, 0x41DFFFFFFFC00000, 0x41F0000000000000,
                0x3FF8000000000000, 0x3FD5555555555555, 0x8000000000000001, 0x800FFFFFFFFFFFFF, 0x0008000000000000, 0x3CA0000000000000, 0x7FE0000000000000]
        return vals
    base = [0, 0x80000000, 0x3F800000, 0xBF800000, 0x40000000, 0x3F000000, 0x7F800000, 0xFF800000, 0x7FC00000, 0x7FA00000, 0xFFC00001, 1, 0x007FFFFF, 0x00800000,
            0x7F7FFFFF, 0xFF7FFFFF, 0x4B000000, 0x4B7FFFFF, 0x4F000000, 0xCF000000, 0x4EFFFFFF, 0x4F800000, 0x3FC00000, 0x3EAAAAAB, 0x80000001, 0x807FFFFF, 0x00400000,
            0x33800000, 0x7F000000]
    return [0xFFFFFFFF00000000 | v for v in base]


def near(v, dbl):
    return (v + rng.choice([-2, -1, 1, 2])) & (M64 if dbl else 0xFFFFFFFF) | (0 if dbl else 0xFFFFFFFF00000000)


def operand(dbl, base_exp):
    k = rng.random()
    if k < 0.25:
        return rng.choice(special(dbl))
    if k < 0.35:
        return near(rng.choice(special(dbl)), dbl)
    if k < 0.45:
        return rng.getrandbits(64) if dbl else (0xFFFFFFFF00000000 | rng.getrandbits(32) if rng.random() < 0.9 else rng.getrandbits(64))
    # a normal number with an exponent near base_exp
    if dbl:
        return rng.getrandbits(1) << 63 | ((1023 + base_exp + rng.randint(-3, 3)) & 0x7FF) << 52 | rng.getrandbits(52)
    return 0xFFFFFFFF00000000 | rng.getrandbits(1) << 31 | ((127 + base_exp + rng.randint(-3, 3)) & 0xFF) << 23 | rng.getrandbits(23)


def int_operand():
    return rng.choice([0, 1, 0xFFFFFFFF, 0x80000000, 0x7FFFFFFF, 2, 0xFFFFFFFE, 0x80000001, rng.getrandbits(32), rng.getrandbits(32), rng.getrandbits(16),
                       rng.getrandbits(24) << 8, 1 << rng.randint(0, 31)])


lines = []
quick = "--quick" in args
for op in ops:
    for dbl in (0, 1):
        if op in (22, 23, 24, 25) and dbl == 1:
            continue
        for rm in range(5):
            for _ in range(N // (4 if quick else 1)):
                be = rng.choice([0, 0, 1, 5, -5, 20, -20, 100 if dbl else 60, -100 if dbl else -60, 500 if dbl else 100, -500 if dbl else -100])
                a, b, c = operand(dbl, be), operand(dbl, be + rng.randint(-60, 60) * (rng.random() < 0.3)), operand(dbl, be + rng.randint(-60, 60) * (rng.random() < 0.3))
                if op in (18, 19):               # near the integer boundaries
                    if rng.random() < 0.5:
                        x = rng.choice([2.0 ** 31, -2.0 ** 31, 2.0 ** 32, 2.5, -2.5, 0.5, -0.5, 1.5, 4294967295.5, 2147483647.5, -2147483648.5, 0.49999, 1e10])
                        x = x * rng.choice([1, 1, 1.0000001, 0.9999999]) if rng.random() < 0.3 else x
                        a = struct.unpack("<Q", struct.pack("<d", x))[0] if dbl else 0xFFFFFFFF00000000 | struct.unpack("<I", struct.pack("<f", x))[0]
                ia = int_operand()
                if op == 4 and rng.random() < 0.7:     # square root: mostly positive operands
                    a &= ~(1 << (63 if dbl else 31))
                fres, ires, flags, wr = R.run(op, dbl, rm, a, b, c, ia)
                lines.append(f"{op:x} {dbl:x} {rm:x} {a:016x} {b:016x} {c:016x} {ia:08x} {fres:016x} {ires:08x} {flags:x} {wr:x}")
rng.shuffle(lines)
open(out, "w").write("\n".join(lines) + "\n")
print(len(lines), "vectors ->", out)
