#!/usr/bin/env python3
"""Runs the curated IP testbenches with Icarus Verilog.

  run_tests.py                         the whole grid of every block (what CI runs)
  run_tests.py uart CLK_DIV=8 PARITY=2 one block at the given parameters (what the server runs per instance)
  run_tests.py --mutants [block]            checks each testbench (or, for blocks with one, the formal proof) fails on
                                       every mutant in mutants/<block>.txt
  run_tests.py --formal                runs the SymbiYosys proofs in formal/

Each testbench prints PASS or FAIL; this script exits non-zero if any run did not print PASS.
"""
import itertools, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCKS = {
    'uart': {'top': 'tb_uart', 'files': ['tb/tb_uart.v', 'rtl/barg_uart.v', 'rtl/barg_fifo.v'],
             'grid': {'CLK_DIV': [8, 13, 100], 'DATA_BITS': [5, 7, 8, 9], 'PARITY': [0, 1, 2], 'STOP_BITS': [1, 2], 'FIFO_AW': [1, 3]}},
    'spi_master': {'top': 'tb_spi_master', 'files': ['tb/tb_spi_master.v', 'rtl/barg_spi_master.v'],
             'grid': {'DATA_W': [1, 8, 13, 32, 64], 'CLK_DIV': [1, 3], 'CPOL': [0, 1], 'CPHA': [0, 1], 'LSB_FIRST': [0, 1], 'CS_W': [1, 3, 4]}},
    'spi_slave': {'top': 'tb_spi_slave', 'files': ['tb/tb_spi_slave.v', 'rtl/barg_spi_slave.v'],
             'grid': {'DATA_W': [1, 8, 13, 32, 64], 'CPOL': [0, 1], 'CPHA': [0, 1], 'LSB_FIRST': [0, 1], 'HP': [4, 7]}},
    'i2c_master': {'top': 'tb_i2c_master', 'files': ['tb/tb_i2c_master.v', 'rtl/barg_i2c_master.v'],
             'grid': {'CLK_DIV': [2, 3, 7, 20], 'STRETCH': [0, 1]}},
    'ram': {'top': 'tb_ram', 'files': ['tb/tb_ram.v', 'rtl/barg_ram.v'],
             'grid': {'DEPTH_W': [4, 6, 10], 'READ_PORTS': [1, 2, 4, 16], 'SEED': [1, 2]}},
    # the floating-point unit: vectors from the exact reference model (tb/fpu_ref.py), generated per run; Verilator
    'fpu': {'top': 'tb_fpu', 'files': ['tb/tb_fpu.v', 'rtl/barg_fpu.v'], 'sim': 'verilator', 'vec': 'tb/gen_fpu_vectors.py',
            'grid': {'SEED': [1, 2, 3]}},
    # AXI4 master (curated) with the memory model behind it, and the memory model alone; Verilator
    'axi_master': {'top': 'tb_axi_master', 'files': ['tb/tb_axi_master.v', 'rtl/barg_axi_master.v', 'rtl/barg_dram.v'], 'sim': 'verilator',
             'grid': {'BEATS_W': [1, 3, 4], 'JITTER': [0, 1], 'READ_LAT': [0, 1, 5], 'WRITE_LAT': [0, 3], 'ERR_EN': [0, 1]}},
    'dram': {'top': 'tb_dram', 'files': ['tb/tb_dram.v', 'rtl/barg_dram.v'], 'sim': 'verilator',
             'grid': {'DEPTH_W': [4, 8], 'READ_LAT': [0, 1, 30], 'WRITE_LAT': [0, 2, 9], 'JITTER': [0, 1], 'ERR_EN': [0, 1]}},
    # the cache array (MODE 0: no state, no dirty bit; MODE 1: 3 state bits and a dirty bit); simulated with Verilator
    'set_assoc': {'top': 'tb_cache', 'files': ['tb/tb_cache.v', 'rtl/barg_cache.v'], 'sim': 'verilator',
             'grid': {'SET_W': [2, 5], 'WAYS': [1, 3, 9], 'LINE_W': [1, 3], 'READ_PORTS': [1, 2], 'MODE': [0, 1]},
             'fix': lambda p: {**{k: v for k, v in p.items() if k != 'MODE'}, 'STATE_W': 3 * p['MODE'], 'DIRTY': p['MODE']}},
    # ADDR_W 0 in the grid stands for the smallest width that addresses every register.
    'axil_regs': {'top': 'tb_axil_regs', 'files': ['tb/tb_axil_regs.v', 'rtl/barg_axil_regs.v'],
             'grid': {'ADDR_W': [0, 12], 'DATA_W': [32, 64], 'N_RW': [1, 3, 8, 64], 'N_RO': [0, 1, 5]},
             'fix': lambda p: {**p, 'ADDR_W': p['ADDR_W'] or min_addr_w(p)}, 'formal': 'axil_regs.sby'},
}

def min_addr_w(p):
    words = p['N_RW'] + p['N_RO']
    return max(1, (words - 1).bit_length()) + (p['DATA_W'] // 8 - 1).bit_length()

def points(b):
    keys = list(b['grid'])
    fix = b.get('fix', lambda p: p)
    return [fix(dict(zip(keys, v))) for v in itertools.product(*(b['grid'][k] for k in keys))]

def verilator_bin():
    return os.environ.get('BARG_VERILATOR') or shutil.which('verilator') or '/home/aura/tools/oss-cad-suite/bin/verilator'

def run_verilator(b, params, seed, d, files):
    """Builds the testbench with Verilator at the given parameters and runs it; (ok, log)."""
    exe = os.path.join(d, 'obj', 'simx')
    args = [verilator_bin(), '--binary', '--timing', '-Wno-fatal', '-Wno-lint', '-Wno-style', '-Wno-WIDTH', '-O1', '-j', '4',
            '--top-module', b['top'], '--Mdir', os.path.join(d, 'obj'), '-o', 'simx']
    for k, v in list(params.items()) + [('SEED', seed)]:
        args += [f'-G{k}={v}']
    c = subprocess.run(args + files, capture_output=True, text=True, env={**os.environ, 'PATH': os.path.dirname(verilator_bin()) + ':' + os.environ['PATH']})
    if c.returncode != 0 or not os.path.exists(exe):
        return False, 'COMPILE: ' + (c.stdout + c.stderr).strip()[-1500:]
    run_args = []
    if b.get('vec'):                       # test vectors made by a script from an exact reference model
        vecf = os.path.join(d, 'vectors.txt')
        g = subprocess.run([sys.executable, os.path.join(HERE, b['vec']), vecf, '--n', '150', '--seed', str(seed)], capture_output=True, text=True)
        if g.returncode:
            return False, 'vector generation failed: ' + g.stderr[-500:]
        run_args = [f'+VEC={vecf}']
    try:
        r = subprocess.run([exe, *run_args], capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        return False, 'FAIL timeout: the simulation ran longer than 30 minutes'
    lines = [l for l in r.stdout.splitlines() if l.startswith(('PASS', 'FAIL'))]
    return bool(lines) and lines[-1].startswith('PASS') and not any(l.startswith('FAIL') for l in lines), '\n'.join(lines[:5])

def run(block, params, seed=1, swap=None):
    b = BLOCKS[block]
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, 'sim.vvp')
        args = ['iverilog', '-g2012', '-o', out, '-s', b['top']]
        for k, v in list(params.items()) + [('SEED', seed)]:
            args += ['-P', f"{b['top']}.{k}={v}"]
        files = [os.path.join(HERE, f) for f in b['files']]
        if swap is not None:                       # (rtl file, its mutated text): simulate the mutant instead
            m = os.path.join(d, os.path.basename(swap[0]))
            open(m, 'w').write(swap[1])
            files = [m if f.endswith(swap[0]) else f for f in files]
        if b.get('sim') == 'verilator':
            return run_verilator(b, params, seed, d, files)
        args += files
        c = subprocess.run(args, capture_output=True, text=True)
        if c.returncode != 0:
            return False, 'COMPILE: ' + c.stderr.strip()
        try:
            r = subprocess.run(['vvp', '-n', out], capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired:
            return False, 'FAIL timeout: the simulation ran longer than 30 minutes'
        lines = [l for l in r.stdout.splitlines() if l.startswith(('PASS', 'FAIL'))]
        return lines[-1:] == ['PASS'], '\n'.join(lines[:5])

def formal(block, rtl_text=None, tasks=()):
    """Runs the block's .sby (on a copy of its RTL, which may be a mutant); True when every task passes."""
    b = BLOCKS[block]
    with tempfile.TemporaryDirectory() as d:
        rtl = [f for f in b['files'] if f.startswith('rtl/')][0]
        os.makedirs(os.path.join(d, 'rtl')); os.makedirs(os.path.join(d, 'formal'))
        open(os.path.join(d, rtl), 'w').write(rtl_text if rtl_text is not None else open(os.path.join(HERE, rtl)).read())
        shutil.copy(os.path.join(HERE, 'formal', b['formal']), os.path.join(d, 'formal'))
        r = subprocess.run(['sby', '-f', b['formal'], *tasks], cwd=os.path.join(d, 'formal'), capture_output=True, text=True, timeout=1800)
        done = [l for l in r.stdout.splitlines() if 'DONE' in l]
        return r.returncode == 0, '\n'.join(done)

def mutants(only=None):
    """Each mutant must fail on at least one grid point (the search stops at the first); prints the survivors."""
    survivors = 0; total = 0
    for block, b in BLOCKS.items():
        if only and block != only:
            continue
        path = os.path.join(HERE, 'mutants', block + '.txt')
        rtl = ([f for f in b['files'] if f.startswith('rtl/') and block in f] or [f for f in b['files'] if f.startswith('rtl/')])[0]
        src = open(os.path.join(HERE, rtl)).read()
        pts = points(b)
        for line in open(path):
            if not line.strip() or line.startswith('#'):
                continue
            old, new = line.rstrip('\n').split(' => ', 1) if ' => ' in line else line.rstrip('\n').split('|', 1)
            assert src.count(old) == 1, f'{block}: mutant text not found once: {old}'
            total += 1
            mutant = src.replace(old, new)
            killed, invalid = False, False
            for i, p in enumerate(pts):
                ok, log = run(block, p, seed=i + 1, swap=(rtl, mutant))
                if not ok:
                    if log.startswith('COMPILE:'):
                        invalid = True        # the mutant does not even compile: not a test of anything
                    else:
                        killed = True
                    break
            if invalid:
                survivors += 1; print('INVALID (does not compile)', block, old, flush=True)
                continue
            if not killed and 'formal' in b:
                killed = not formal(block, mutant)[0]
            if not killed:
                survivors += 1; print('SURVIVED', block, old, flush=True)
    print(f'{total - survivors}/{total} mutants killed')
    return 1 if survivors else 0

def main(argv):
    if argv[:1] == ['--mutants']:
        return mutants(argv[1] if len(argv) > 1 else None)
    if argv == ['--formal']:
        bad = 0
        for block, b in BLOCKS.items():
            if 'formal' in b:
                ok, log = formal(block); bad += not ok; print(('PASS ' if ok else 'FAIL ') + block + '\n' + log)
        return 1 if bad else 0
    if argv:
        block, params = argv[0], dict(a.split('=', 1) for a in argv[1:])
        ok, log = run(block, params)
        print(('PASS ' if ok else 'FAIL ') + block + ' ' + ' '.join(argv[1:]) + ('' if ok else '\n' + log))
        return 0 if ok else 1
    bad = 0; n = 0
    for block, b in BLOCKS.items():
        for i, params in enumerate(points(b)):
            n += 1
            ok, log = run(block, params, seed=i + 1)
            if not ok:
                bad += 1; print('FAIL', block, params, log, flush=True)
    print(f'{n - bad}/{n} configurations pass')
    return 1 if bad else 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
