"""Golden model of `bp_mux`. Combinational. Written by hand."""


def golden_bp_mux(from_alu, from_fp, sel):
    return {"y": from_fp if sel else from_alu}
