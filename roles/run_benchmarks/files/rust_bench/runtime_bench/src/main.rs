fn main() {
    const DEFAULT_ITERATIONS: u64 = 50_000_000;
    let iterations = std::env::var("RUST_RUNTIME_ITERATIONS")
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(DEFAULT_ITERATIONS);
    let mut x: u64 = 42;
    let mut acc: u64 = 0;
    for _iteration in 0..iterations {
        x = x.wrapping_mul(6364136223846793005).wrapping_add(1);
        acc ^= x.rotate_left(13);
    }
    println!("{}", acc);
}
