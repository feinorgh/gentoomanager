/* Spectral norm — adapted from the Computer Language Benchmarks Game.
   Compile: gcc -O3 -march=native -ffast-math -lm -o bench_spectral_norm bench_spectral_norm.c
   Run:     ./bench_spectral_norm 1000       */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

static inline double A(int i, int j) {
    return 1.0 / ((double)((i+j)*(i+j+1)/2 + i + 1));
}

static void mult_Av(const double *v, double *out, int n) {
    for (int i = 0; i < n; i++) {
        double s = 0.0;
        for (int j = 0; j < n; j++) s += A(i,j) * v[j];
        out[i] = s;
    }
}
static void mult_AtV(const double *v, double *out, int n) {
    for (int i = 0; i < n; i++) {
        double s = 0.0;
        for (int j = 0; j < n; j++) s += A(j,i) * v[j];
        out[i] = s;
    }
}

int main(int argc, char **argv) {
    int N = argc > 1 ? atoi(argv[1]) : 1000;
    double *u = malloc(N * sizeof(double));
    double *v = malloc(N * sizeof(double));
    double *tmp = malloc(N * sizeof(double));
    for (int i = 0; i < N; i++) u[i] = 1.0;
    for (int i = 0; i < 10; i++) {
        mult_Av(u, tmp, N);  mult_AtV(tmp, v, N);
        mult_Av(v, tmp, N);  mult_AtV(tmp, u, N);
    }
    double vBv = 0.0, vv = 0.0;
    for (int i = 0; i < N; i++) { vBv += u[i]*v[i]; vv += v[i]*v[i]; }
    printf("%.9f\n", sqrt(vBv/vv));
    free(u); free(v); free(tmp);
    return 0;
}
