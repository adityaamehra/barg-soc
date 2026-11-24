"""Golden model of the core clock gate (block `core_gate`). Written by hand.

The gated clock gclk follows clk while the enable is on and stays low while it is off. The enable is latched while clk is low
(a latch, transparent when clk is 0): q = en | rst, and gclk = clk & q. So gclk is 0 whenever clk is 0 (this is all a bench that
samples between clock edges can see)."""


def golden_core_gate(trace):
    return [{"gclk": 0} for _ in trace]


def traces(rng):
    return [[{"en": rng.getrandbits(1), "rst": int(rng.random() < 0.1)} for _ in range(40)] for _ in range(4)]
