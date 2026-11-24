"""Golden model of `fp_resmux`. Combinational. Written by hand."""


def golden_fp_resmux(from_alu, from_fp, sel):
    return {"y": from_fp if sel else from_alu}
