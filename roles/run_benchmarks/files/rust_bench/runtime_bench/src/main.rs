fn main() {
    let mut x: u64 = 42;
    let mut acc: u64 = 0;
    for _ in 0..5_000_000 {
        x = x.wrapping_mul(6364136223846793005).wrapping_add(1);
        acc ^= x.rotate_left(13);
    }
    println!("{}", acc);
}
