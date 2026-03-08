/* Mandelbrot set — adapted from the Computer Language Benchmarks Game.
   Compile: gcc -O3 -march=native -ffast-math -o bench_mandelbrot bench_mandelbrot.c
   Run:     ./bench_mandelbrot 4000          */
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    int N = argc > 1 ? atoi(argv[1]) : 4000;
    long inside = 0;
    for (int y = 0; y < N; y++) {
        double ci = 2.0 * y / N - 1.0;
        for (int x = 0; x < N; x++) {
            double cr = 2.5 * x / N - 1.75;
            double zr = 0.0, zi = 0.0;
            int k = 0;
            while (k < 50) {
                double zr2 = zr*zr, zi2 = zi*zi;
                if (zr2 + zi2 > 4.0) break;
                zi = 2.0*zr*zi + ci;
                zr = zr2 - zi2 + cr;
                k++;
            }
            if (k == 50) inside++;
        }
    }
    printf("%ld\n", inside);
    return 0;
}
