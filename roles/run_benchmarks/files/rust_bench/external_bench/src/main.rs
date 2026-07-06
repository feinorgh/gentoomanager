use regex::Regex;
use serde_json::Value;
use std::fs;

fn main() {
    let data = fs::read_to_string("fixtures/external_input.json").expect("fixture");
    let value: Value = serde_json::from_str(&data).expect("json");
    let re = Regex::new(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}").expect("regex");
    let mut count = 0usize;
    if let Some(arr) = value.as_array() {
        for entry in arr {
            if let Some(s) = entry.as_str() {
                count += re.find_iter(s).count();
            }
        }
    }
    println!("{}", count);
}
