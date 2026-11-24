"""Golden model of `px_pick`: the RGB565 pixel chosen from a word of two pixels. Combinational. Written by hand."""


def golden_px_pick(word, half, de):
    pix = (word >> 16 if half & 1 else word) & 0xFFFF
    if not de & 1:
        return {"r": 0, "g": 0, "b": 0}
    return {"r": pix >> 11 & 31, "g": pix >> 5 & 63, "b": pix & 31}


def vectors(rng):
    return [{"word": rng.getrandbits(32), "half": rng.getrandbits(1), "de": int(rng.random() < 0.8)} for _ in range(1500)]
