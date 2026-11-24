"""Golden model of `fp_csr`: fflags, frm, mstatus.FS and their CSR read/legality patches. Clocked. Written by hand. None before the first reset."""


def golden_fp_csr(trace):
    s = None
    out = []
    for i in trace:
        if s is None:
            out.append({k: None for k in ("fs", "frm", "rdata_out", "illegal_out")})
        else:
            addr = i["inst"] >> 20 & 0xFFF
            rd = i["rdata_in"]
            if addr == 1:
                rd = s["fflags"]
            elif addr == 2:
                rd = s["frm"]
            elif addr == 3:
                rd = s["frm"] << 5 | s["fflags"]
            elif addr in (0x300, 0x100):
                rd = (rd & ~(3 << 13)) | s["fs"] << 13 | ((1 << 31) if s["fs"] == 3 else 0)
            elif addr == 0x301:
                rd |= 0x28
            acc = i["csrop"] in (1, 2, 3, 4)
            ill = int(s["fs"] == 0) if acc and addr in (1, 2, 3) else i["illegal_in"]
            out.append({"fs": s["fs"], "frm": s["frm"], "rdata_out": rd, "illegal_out": ill})
        if i["rst"] & 1:
            s = {"fflags": 0, "frm": 0, "fs": 0}
        elif s is not None:
            addr = i["inst"] >> 20 & 0xFFF
            if i["csr_we"]:
                n = i["nval"]
                if addr == 1:
                    s["fflags"], s["fs"] = n & 31, 3
                elif addr == 2:
                    s["frm"], s["fs"] = n & 7, 3
                elif addr == 3:
                    s["frm"], s["fflags"], s["fs"] = n >> 5 & 7, n & 31, 3
                elif addr in (0x300, 0x100):
                    s["fs"] = n >> 13 & 3
            else:
                s["fflags"] |= i["flags_set"]
                if i["dirty_set"]:
                    s["fs"] = 3
    return out


def traces(rng):
    out = []
    addrs = (1, 2, 3, 0x300, 0x100, 0x301, 0x305, 0x7FF, 0xFFF)
    for _ in range(40):
        t = [{"rst": 1, "inst": 0, "csrop": 0, "csr_we": 0, "nval": 0, "flags_set": 0, "dirty_set": 0, "rdata_in": 0, "illegal_in": 0}]
        for _ in range(150):
            we = int(rng.random() < 0.3)
            t.append({"rst": int(rng.random() < 0.01), "inst": (rng.getrandbits(32) & 0xFFFFF) | rng.choice(addrs) << 20,
                      "csrop": rng.choice((0, 1, 2, 3, 4, 1, 2, 3, 5, 6, 7)), "csr_we": we, "nval": rng.getrandbits(32),
                      "flags_set": 0 if we else rng.choice((0, 0, rng.getrandbits(5))), "dirty_set": 0 if we else int(rng.random() < 0.15),
                      "rdata_in": rng.getrandbits(32), "illegal_in": rng.getrandbits(1)})
        out.append(t)
    return out
