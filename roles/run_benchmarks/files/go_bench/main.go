package main

import (
	"fmt"
	"math/rand"
	"sort"
)

const N = 256

func main() {
	r := rand.New(rand.NewSource(42))
	a := make([]float64, N*N)
	b := make([]float64, N*N)
	c := make([]float64, N*N)
	for i := range a {
		a[i] = r.Float64()
		b[i] = r.Float64()
	}
	for i := 0; i < N; i++ {
		for j := 0; j < N; j++ {
			sum := 0.0
			for k := 0; k < N; k++ {
				sum += a[i*N+k] * b[k*N+j]
			}
			c[i*N+j] = sum
		}
	}
	sort.Float64s(c)
	fmt.Printf("result: %f\n", c[len(c)/2])
}
