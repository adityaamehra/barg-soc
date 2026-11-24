"""Golden model of the graphics write-back select (block `gfx_sel`). Combinational. Never shown to the generator.

y = gfx_y | tex_y | z_y when gfx is 1, else alu_y (128 bits each): a graphics instruction's result (the raster unit's, the texture
unit's or the depth unit's; each is 0 for instructions that are not its own) replaces the arithmetic unit's on its way to the
write-back selector.
"""


def golden_gfx_sel(gfx, alu_y, gfx_y, tex_y, z_y):
    return {"y": (gfx_y | tex_y | z_y) if gfx & 1 else alu_y}
