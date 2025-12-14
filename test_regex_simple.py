#!/usr/bin/env python3
"""Simple test to validate season/episode pattern matching"""

import re as regex

# Test just the season/episode part
test_cases = [
    ("S01E01", "Standard format"),
    ("S01E02", "Standard format ep 2"),
    ("S01.E01", "With dot separator"),
    ("1x01", "Legacy format"),
    ("season.01", "Explicit season"),
    ("season.1", "Explicit season no zero"),
]

# OLD season pattern part
old_season_pattern = r"(season\.1[^0-9e]|season\.01[^0-9e]|S01[^0-9e])"

# NEW season pattern part
new_season_pattern = r"(season\.1[^0-9]|season\.01[^0-9]|S01[^0-9]|S01E[0-9]+|1x[0-9]+)"

print("=" * 80)
print("SEASON/EPISODE PATTERN TEST")
print("=" * 80)
print()

print("OLD PATTERN:", old_season_pattern)
print()
old_matches = 0
for test, desc in test_cases:
    match = regex.search(old_season_pattern, test, regex.I)
    if match:
        old_matches += 1
        print(f"[OK] {test:20s} - {desc}")
    else:
        print(f"[XX] {test:20s} - {desc}")

print()
print(f"OLD PATTERN: {old_matches}/{len(test_cases)} matches")
print()
print("=" * 80)
print()

print("NEW PATTERN:", new_season_pattern)
print()
new_matches = 0
for test, desc in test_cases:
    match = regex.search(new_season_pattern, test, regex.I)
    if match:
        new_matches += 1
        print(f"[OK] {test:20s} - {desc}")
    else:
        print(f"[XX] {test:20s} - {desc}")

print()
print(f"NEW PATTERN: {new_matches}/{len(test_cases)} matches")
print()
print("=" * 80)
print()

print("RESULT:")
if new_matches > old_matches:
    print(f"[OK] FIX WORKS! Went from {old_matches} to {new_matches} matches (+{new_matches-old_matches})")
else:
    print(f"[XX] No improvement: {old_matches} -> {new_matches}")
print()
