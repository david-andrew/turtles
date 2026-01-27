"""
UUID grammar as defined by RFC 4122.
Supports all UUID versions: 1, 3, 4, 5.

TODO: test this
"""

from turtles import Rule, char, repeat, exactly, sequence

hex = char['0-9A-Fa-f']

class UUID(Rule):
    time_low: repeat[hex, exactly[8]]
    '-'
    time_mid: repeat[hex, exactly[4]]
    '-'
    time_high_and_version: sequence[char['1-5'], repeat[hex, exactly[3]]]
    '-'
    clock_seq_and_variant: sequence[char['89abAB'], repeat[hex, exactly[3]]]
    '-'
    node: repeat[hex, exactly[12]]
