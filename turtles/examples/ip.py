"""
IPv4 and IPv6 address grammars

TODO: test this
"""

from turtles import Rule, char, repeat, at_least, at_most, separator, optional, exactly, sequence, either


# TODO: this implies it would be nice to have a disambiguation filter for numbers less than 256
#       perhaps a literal "validation filter" where user can write a function that would check if a parse was valid or not, and reject if not valid
class Octet(Rule, int):
    value: either[
        '0',                                             # 0
        sequence[char['1-9'], optional[char['0-9']]],    # 1-99
        sequence['1', repeat[char['0-9'], exactly[2]]],  # 100-199
        sequence['2', char['0-4'], char['0-9']],         # 200-249
        sequence['25', char['0-5']],                     # 250-255
    ]

class IPv4(Rule):
    octet1: Octet
    '.'
    octet2: Octet
    '.'
    octet3: Octet
    '.'
    octet4: Octet


H16 = repeat[hex, at_least[1], at_most[4]]
LS32 = either[
    sequence[H16, r':', H16],
    IPv4,
]


class IPv6Full(Rule):
    seq: sequence[repeat[H16, separator[r':'], exactly[6]], LS32]

class IPv6Compact(Rule):
    seq: either[
        sequence[r"::"],  # all zeros

        # :: + 1..7 hextets
        sequence[r"::", repeat[H16, separator[r":"], at_least[1], at_most[7]]],

        # 1..7 hextets + ::
        sequence[repeat[H16, separator[r":"], at_least[1], at_most[7]], r"::"],

        # 1..6 hextets + :: + 1..(7-left) hextets  (enumerated)
        sequence[repeat[H16, separator[r":"], exactly[1]], r"::", repeat[H16, separator[r":"], at_least[1], at_most[6]]],
        sequence[repeat[H16, separator[r":"], exactly[2]], r"::", repeat[H16, separator[r":"], at_least[1], at_most[5]]],
        sequence[repeat[H16, separator[r":"], exactly[3]], r"::", repeat[H16, separator[r":"], at_least[1], at_most[4]]],
        sequence[repeat[H16, separator[r":"], exactly[4]], r"::", repeat[H16, separator[r":"], at_least[1], at_most[3]]],
        sequence[repeat[H16, separator[r":"], exactly[5]], r"::", repeat[H16, separator[r":"], at_least[1], at_most[2]]],
        sequence[repeat[H16, separator[r":"], exactly[6]], r"::", H16],

        # 1..6 hextets + :: + LS32 (already in your version, but keep it)
        sequence[repeat[H16, separator[r":"], at_least[1], at_most[6]], r"::", LS32],
    ]

IPv6 = IPv6Full | IPv6Compact
