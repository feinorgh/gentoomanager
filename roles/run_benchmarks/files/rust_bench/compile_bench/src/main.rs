fn matmul(a: &[[f64; 128]; 128], b: &[[f64; 128]; 128]) -> [[f64; 128]; 128] {
    let mut c = [[0.0f64; 128]; 128];
    for i in 0..128 {
        for j in 0..128 {
            let mut sum = 0.0;
            for k in 0..128 { sum += a[i][k] * b[k][j]; }
            c[i][j] = sum;
        }
    }
    c
}
fn main() {
    let mut a = [[0.0f64; 128]; 128];
    let mut b = [[0.0f64; 128]; 128];
    let mut seed: u64 = 42;
    for i in 0..128 {
        for j in 0..128 {
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
            a[i][j] = (seed >> 33) as f64 / (1u64 << 31) as f64;
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
            b[i][j] = (seed >> 33) as f64 / (1u64 << 31) as f64;
        }
    }
    let c = matmul(&a, &b);
    println!("result: {}", c[64][64]);
}
