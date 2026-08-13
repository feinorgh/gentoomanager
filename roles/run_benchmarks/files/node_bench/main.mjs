#!/usr/bin/env node

import crypto from "node:crypto";

function benchPrimeCount(limit) {
  const sieve = new Uint8Array(limit + 1).fill(1);
  sieve[0] = 0;
  sieve[1] = 0;

  for (let i = 2; i * i <= limit; i += 1) {
    if (!sieve[i]) {
      continue;
    }
    for (let j = i * i; j <= limit; j += i) {
      sieve[j] = 0;
    }
  }

  let count = 0;
  for (const value of sieve) {
    count += value;
  }
  return count;
}

function benchHash(rounds) {
  const payload = Buffer.alloc(1024 * 1024, 0x5a);
  let digest = "";
  for (let index = 0; index < rounds; index += 1) {
    digest = crypto.createHash("sha256").update(payload).digest("hex");
  }
  return digest;
}

const primes = benchPrimeCount(2_000_000);
const digest = benchHash(200);
console.log(`${primes}:${digest.slice(0, 16)}`);
