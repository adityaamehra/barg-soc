"""Golden model of the pipeline register `dx_reg` of `simt-gpu-gfx` (written by gfx/build_gfx.py from its field list; the core's fields plus gfx and gfx_op).

Every output <f>_out shows the value its input <f>_in had at the last rising edge at which the register loaded. At each rising
edge: rst or clear sets every field to 0 (valid becomes 0, a bubble); otherwise when hold is 1 every field keeps its value;
otherwise every field takes its input. Before the first reset every field is unknown.
"""

FIELDS = ['valid', 'wid', 'pc', 'tmask', 'rd', 'unit', 'alu_op', 'a_sel', 'b_sel', 'wb_src', 'regwrite', 'ctrl', 'br_op', 'mem_store', 'mem_size', 'md_op', 'simt_op', 'simt_mode', 'tensor_op', 'gfx', 'gfx_op', 'csr_addr', 'illegal', 'imm', 'a', 'b']


class PipeReg:
    def __init__(self):
        self.state = None

    def outputs(self, i):
        return {f + "_out": None if self.state is None else self.state[f] for f in FIELDS}

    def edge(self, i):
        if i["rst"] & 1 or i["clear"] & 1:
            self.state = {f: 0 for f in FIELDS}
        elif self.state is not None and not i["hold"] & 1:
            self.state = {f: i[f + "_in"] for f in FIELDS}


def golden_dx_reg(trace):
    m, out = PipeReg(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out
