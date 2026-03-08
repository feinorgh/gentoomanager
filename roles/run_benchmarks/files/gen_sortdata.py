#!/usr/bin/env python3
"""Generate a deterministic random text file used by coreutils benchmarks.

Creates sortdata.txt in the current working directory containing 500 000
lines of 80-character alphanumeric strings with a fixed random seed, so
the file is identical on every run and the benchmark is reproducible.
"""

import random
import string

random.seed(42)
chars = string.ascii_letters + string.digits
with open("sortdata.txt", "w") as f:
    for _ in range(500_000):
        f.write("".join(random.choices(chars, k=80)) + "\n")
