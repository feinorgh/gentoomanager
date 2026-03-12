#!/usr/bin/env python3
"""Generate a multi-file C benchmark project for compilation speed tests.

Creates a directory containing a Makefile and N independent C source modules
(default 30), each ~220 lines of non-trivial arithmetic, sort, and hashing
code.  The full project (~6600 lines) exercises the compiler's front-end,
optimiser, and linker at a meaningful scale.

Usage::

    python3 scripts/generate_multifile_bench.py <output_dir> [--modules N]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Makefile template
# ---------------------------------------------------------------------------

MAKEFILE = """\
# Auto-generated Makefile for multi-file compilation benchmark.
CC      ?= gcc
CFLAGS  ?= -O2
SRCS    := $(wildcard mod_*.c) main.c
OBJS    := $(SRCS:.c=.o)
BIN     := multifile_bench

.PHONY: all clean

all: $(BIN)

$(BIN): $(OBJS)
\t$(CC) $(CFLAGS) -o $@ $^ -lm

%.o: %.c
\t$(CC) $(CFLAGS) -c -o $@ $<

clean:
\t@rm -f $(OBJS) $(BIN)
"""

# ---------------------------------------------------------------------------
# main.c template
# ---------------------------------------------------------------------------

MAIN_HEADER = """\
/* main.c — auto-generated benchmark driver */
#include <stdio.h>
#include <stdlib.h>

"""

MAIN_FOOTER_TMPL = """\
int main(void)
{{
    double total = 0.0;
    unsigned seed = 0xdeadbeef;
{calls}
    printf("total: %.10f\\n", total);
    return 0;
}}
"""

# ---------------------------------------------------------------------------
# Per-module template
# ---------------------------------------------------------------------------
# Uses old-style % formatting so braces in the C code are literal.

MODULE_TMPL = """\
/* mod_{n:02d}.c — auto-generated benchmark module {n:02d} */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define MOD_ID    {n}
#define MOD_SIZE  512

typedef struct {{
    unsigned key;
    double   val;
    double   wgt;
    char     tag[24];
}} rec{n}_t;

static rec{n}_t  g_rec_{n}[MOD_SIZE];
static double    g_aux_{n}[MOD_SIZE];

static unsigned lcg_{n}(unsigned s)
{{
    return s * 1664525u + 1013904223u ^ ((unsigned){n} * 2654435761u);
}}

void mod{n}_init(unsigned seed)
{{
    unsigned s = seed ^ ((unsigned){n} * 6364136223u);
    for (int i = 0; i < MOD_SIZE; i++) {{
        s = lcg_{n}(s);
        g_rec_{n}[i].key = s;
        g_rec_{n}[i].val = (s & 0xffffu) * (1.0 / 65536.0);
        s = lcg_{n}(s);
        g_rec_{n}[i].wgt = (s & 0xffffu) * (1.0 / 65536.0) + 0.001;
        snprintf(g_rec_{n}[i].tag, 24, "m{n:02d}_%06x", s & 0xffffffu);
        g_aux_{n}[i] = 0.0;
    }}
}}

double mod{n}_wsum(void)
{{
    double a = 0.0;
    for (int i = 0; i < MOD_SIZE; i++)
        a += g_rec_{n}[i].val * g_rec_{n}[i].wgt;
    return a;
}}

static int cmp{n}(const void *a, const void *b)
{{
    const rec{n}_t *ra = (const rec{n}_t *)a;
    const rec{n}_t *rb = (const rec{n}_t *)b;
    return (ra->val > rb->val) - (ra->val < rb->val);
}}

void mod{n}_sort(void)
{{
    qsort(g_rec_{n}, MOD_SIZE, sizeof(rec{n}_t), cmp{n});
}}

int mod{n}_bisect(double t)
{{
    int lo = 0, hi = MOD_SIZE - 1;
    while (lo <= hi) {{
        int m = lo + (hi - lo) / 2;
        if      (g_rec_{n}[m].val < t) lo = m + 1;
        else if (g_rec_{n}[m].val > t) hi = m - 1;
        else return m;
    }}
    return ~lo;
}}

double mod{n}_compute(int iter)
{{
    double acc = (double){n} * 1e-3;
    for (int r = 0; r < iter; r++) {{
        for (int i = 0; i < MOD_SIZE; i++) {{
            double v = g_rec_{n}[i].val + acc * 1e-7;
            double w = g_rec_{n}[i].wgt;
            g_aux_{n}[i] = sqrt(v * v + w * w)
                         + sin(acc + (double)i * 0.01)
                         * cos(w + (double)r * 1e-3);
            acc += g_aux_{n}[i] * 1e-9;
        }}
    }}
    return acc;
}}

unsigned mod{n}_hash(const void *buf, unsigned len)
{{
    const unsigned char *p = (const unsigned char *)buf;
    unsigned h = 2166136261u ^ ((unsigned){n} * 16777619u);
    for (unsigned i = 0; i < len; i++) {{
        h ^= p[i];
        h *= 16777619u;
        h ^= h >> 13;
    }}
    return h;
}}

void mod{n}_transform(double scale, double shift)
{{
    for (int i = 0; i < MOD_SIZE; i++) {{
        double v = g_rec_{n}[i].val * scale + shift;
        v -= floor(v);
        g_rec_{n}[i].val = v;
    }}
}}

void mod{n}_prefix(double *out, int out_n)
{{
    double s = 0.0;
    int sz = MOD_SIZE < out_n ? MOD_SIZE : out_n;
    for (int i = 0; i < sz; i++) {{
        s += g_rec_{n}[i].val * g_rec_{n}[i].wgt;
        out[i] = s;
    }}
}}

double mod{n}_integrate(int lo, int hi)
{{
    int n = hi - lo;
    if (n < 2)
        return n == 1 ? g_rec_{n}[lo].val * g_rec_{n}[lo].wgt : 0.0;
    double s = g_rec_{n}[lo].val * g_rec_{n}[lo].wgt
             + g_rec_{n}[hi - 1].val * g_rec_{n}[hi - 1].wgt;
    for (int i = lo + 1; i < hi - 1; i++)
        s += 2.0 * g_rec_{n}[i].val * g_rec_{n}[i].wgt;
    return s * 0.5;
}}

void mod{n}_stats(double *mn, double *mx, double *mean, double *var)
{{
    double lo = g_rec_{n}[0].val, hi = lo, sum = 0.0, sum2 = 0.0;
    for (int i = 0; i < MOD_SIZE; i++) {{
        double v = g_rec_{n}[i].val;
        if (v < lo) lo = v;
        if (v > hi) hi = v;
        sum  += v;
        sum2 += v * v;
    }}
    *mn   = lo;
    *mx   = hi;
    *mean = sum  / MOD_SIZE;
    *var  = sum2 / MOD_SIZE - (*mean) * (*mean);
}}

double mod{n}_reduce(int op)
{{
    double r = 0.0;
    int i;
    switch ((op + {n}) % 5) {{
    case 0: for (i = 0; i < MOD_SIZE; i++) r += g_rec_{n}[i].val; break;
    case 1: r = g_rec_{n}[0].val;
            for (i = 1; i < MOD_SIZE; i++)
                if (g_rec_{n}[i].val < r) r = g_rec_{n}[i].val;
            break;
    case 2: r = g_rec_{n}[0].val;
            for (i = 1; i < MOD_SIZE; i++)
                if (g_rec_{n}[i].val > r) r = g_rec_{n}[i].val;
            break;
    case 3: for (i = 0; i < MOD_SIZE; i++) r += g_aux_{n}[i]; break;
    case 4: for (i = 0; i < MOD_SIZE; i++)
                r += mod{n}_hash(g_rec_{n}[i].tag, 24) * 1e-9;
            break;
    }}
    return r;
}}

void mod{n}_report(void)
{{
    double mn, mx, mean, var;
    mod{n}_stats(&mn, &mx, &mean, &var);
    printf("mod%02d: wsum=%.6f cpt=%.6f h=%08x "
           "mn=%.4f mx=%.4f mean=%.4f var=%.6f\\n",
           MOD_ID, mod{n}_wsum(), mod{n}_compute(1),
           mod{n}_hash(g_rec_{n}, sizeof(g_rec_{n})),
           mn, mx, mean, var);
}}

double mod{n}_run(unsigned seed)
{{
    double out[MOD_SIZE];
    mod{n}_init(seed);
    mod{n}_sort();
    mod{n}_transform(1.0 + (double){n} * 0.01, (double){n} * 0.001);
    mod{n}_prefix(out, MOD_SIZE);
    double c = mod{n}_compute(2);
    double ig = mod{n}_integrate(0, MOD_SIZE / 2);
    double rd = mod{n}_reduce({n} % 5);
    return c + ig + rd + out[MOD_SIZE / 2];
}}
"""


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def gen_module(n: int, proj_dir: Path) -> None:
    """Write mod_NN.c for module index n."""
    content = MODULE_TMPL.format(n=n)
    (proj_dir / f"mod_{n:02d}.c").write_text(content)


def gen_main(n_modules: int, proj_dir: Path) -> None:
    """Write main.c that calls run() on every module."""
    decls = "\n".join(
        f"double mod{n}_run(unsigned seed);"
        for n in range(n_modules)
    )
    calls = "\n".join(
        f"    total += mod{n}_run(seed ^ 0x{(n * 0x9e3779b9) & 0xFFFFFFFF:08x}u);"
        for n in range(n_modules)
    )
    content = MAIN_HEADER + decls + "\n\n" + MAIN_FOOTER_TMPL.format(calls=calls)
    (proj_dir / "main.c").write_text(content)


def generate(proj_dir: Path, n_modules: int) -> None:
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "Makefile").write_text(MAKEFILE)
    for n in range(n_modules):
        gen_module(n, proj_dir)
    gen_main(n_modules, proj_dir)
    total_lines = sum(
        p.read_text().count("\n")
        for p in proj_dir.glob("*.c")
    )
    print(
        f"Generated {n_modules} modules + main.c in {proj_dir} "
        f"({total_lines} total lines)"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path,
                        help="Directory to write the project into")
    parser.add_argument("--modules", type=int, default=30,
                        help="Number of C modules to generate (default: 30)")
    args = parser.parse_args()
    generate(args.output_dir, args.modules)
    return 0


if __name__ == "__main__":
    sys.exit(main())
