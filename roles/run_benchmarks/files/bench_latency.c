/* Pointer-chasing memory latency benchmark.
   Allocates a 64 MB array (exceeds typical L3 cache), builds a random
   permutation, then traverses it sequentially — each access is a cache miss.
   Compile: gcc -O2 -o bench_latency bench_latency.c
   Run:     ./bench_latency                               */
#include <stdio.h>
#include <stdlib.h>

#define N (1 << 23)   /* 8M entries × 8 bytes = 64 MB */

int main(void) {
    size_t *arr = malloc(N * sizeof(size_t));
    if (!arr) { perror("malloc"); return 1; }

    /* Sequential initialisation */
    for (size_t i = 0; i < N; i++) arr[i] = i;

    /* Fisher-Yates shuffle using LCG (no stdlib rand — deterministic) */
    unsigned long long rng = 0xdeadbeefcafe1234ULL;
    for (size_t i = N - 1; i > 0; i--) {
        rng = rng * 6364136223846793005ULL + 1442695040888963407ULL;
        size_t j = (rng >> 33) % (i + 1);
        size_t tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
    }

    /* Chase the chain — every access is (nearly) a cache miss */
    volatile size_t idx = 0;
    for (size_t k = 0; k < N; k++) idx = arr[idx];

    printf("%zu\n", (size_t)idx);
    free(arr);
    return 0;
}
