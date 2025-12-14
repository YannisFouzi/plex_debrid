#!/usr/bin/env python3
"""Test script to validate the season regex pattern fix"""

import re as regex

# Test data from actual releases in LOG.txt
test_releases = [
    "Pluribus.S01E01.Noi.siamo.noi.ITA.ENG.2160p.ATVP.WEB-DL.DDP5.1.Atmos.DV.HDR.H.265-MeM.GP.mkv",
    "Pluribus.S01E01-02.2160p.ATVP.WEB-DL.DDP5.1.Atmos.ITA-ENG.DV.HDR.H.265-G66",
    "Pluribus.1x01.Noi.Siamo.Noi.2160p.WEB-DL.H265.HDR10+.Dolby.Vision.Ita.Eng.AC3.5.1.Multisub.iDN_CreW",
    "Pluribus.S01E01.We.Is.Us.2160p.ATVP.WEB-DL.DDP5.1.DV.H.265-NTb",
    "Pluribus.S01E01.We.Is.Us.1080p.ATVP.WEB-DL.DDP5.1.Atmos.H.264-FLUX",
    "Pluribus.2025.S01.E01.E02.1080p.ATVP.WEB-DL.DDP5.1.Atmos.H264.Dual.YG",
    "Pluribus.S01E01.MULTI.1080p.WEB.H264-HiggsBoson",
    "Pluribus.[HDTV.1080p][Cap.101]",
]

# OLD pattern (broken)
def old_pattern(index=1, year=2025):
    title = "plur1bus"
    return (
        "(.*?)("
        + title
        + ":?.)(series.|[^A-Za-z0-9]+)?(\(?"
        + str(year)
        + "\)?.)?(season."
        + str(index)
        + "[^0-9e]|season."
        + str("{:02d}".format(index))
        + "[^0-9e]|S"
        + str("{:02d}".format(index))
        + "[^0-9e])"
    )

# NEW pattern (fixed)
def new_pattern(index=1, year=2025):
    title = "plur1bus"
    season_num = str(index)
    season_02d = str("{:02d}".format(index))
    return (
        "(.*?)("
        + title
        + ":?.)(series.|[^A-Za-z0-9]+)?(\(?"
        + str(year)
        + "\)?.)?(season."
        + season_num
        + "[^0-9]|season."
        + season_02d
        + "[^0-9]|S"
        + season_02d
        + "[^0-9]|S"
        + season_02d
        + "E[0-9]+|"
        + season_num
        + "x[0-9]+)"
    )

print("=" * 80)
print("REGEX PATTERN FIX VALIDATION TEST")
print("=" * 80)
print()

# Test OLD pattern
print("OLD PATTERN (BROKEN):")
print(old_pattern())
print()
old_matches = 0
for release in test_releases:
    match = regex.match(old_pattern(), release, regex.I)
    if match:
        old_matches += 1
        print(f"[OK] MATCH: {release[:80]}")
    else:
        print(f"[XX] FAIL:  {release[:80]}")

print()
print(f"OLD PATTERN RESULTS: {old_matches}/{len(test_releases)} matches ({old_matches*100//len(test_releases)}%)")
print()
print("=" * 80)
print()

# Test NEW pattern
print("NEW PATTERN (FIXED):")
print(new_pattern())
print()
new_matches = 0
for release in test_releases:
    match = regex.match(new_pattern(), release, regex.I)
    if match:
        new_matches += 1
        print(f"[OK] MATCH: {release[:80]}")
    else:
        print(f"[XX] FAIL:  {release[:80]}")

print()
print(f"NEW PATTERN RESULTS: {new_matches}/{len(test_releases)} matches ({new_matches*100//len(test_releases)}%)")
print()
print("=" * 80)
print()

# Summary
print("SUMMARY:")
print(f"  Old pattern: {old_matches}/{len(test_releases)} matches ({old_matches*100//len(test_releases)}%)")
print(f"  New pattern: {new_matches}/{len(test_releases)} matches ({new_matches*100//len(test_releases)}%)")
print(f"  Improvement: +{new_matches - old_matches} matches (+{(new_matches - old_matches)*100//len(test_releases)}%)")
print()

if new_matches > old_matches:
    print("[OK] FIX IS SUCCESSFUL - New pattern matches more releases!")
else:
    print("[XX] FIX FAILED - New pattern does not improve matching")
print()
print("=" * 80)
