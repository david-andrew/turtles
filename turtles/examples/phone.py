"""
Phone number grammar as defined by E.164, as well as common human-readable extensions.

TODO: test this

+1 (415) 555-2671
+1 415 555 2671
+44 20 7946 0123
(415) 555-2671
415-555-2671
+1 (415) 555-2671 ext 123
+44 20 7946 0123 x9
"""

from turtles import Rule, char, repeat, at_most, optional, exactly, sequence, either


class E164(Rule):
    '+'
    digits: sequence[char['1-9'], repeat[char['0-9'], at_most[14]]]


# Common separators people type between digit groups
Sep = char[" -.\u00A0"]  # space, hyphen, dot, NBSP

# Optional extension markers (choose what you want to allow)
ExtMarker = either[r"x", r"X", r"ext", r"ext.", r"#"]


class USPhone(Rule):
    # TODO: would be nice to have a helper for optionally wrapping something. e.g. wrap[A, seq1, seq2, ...[, None]]
    area_code: either[
        sequence[char['2-9'], char['0-9'], char['0-9']],
        sequence[r'(', char['2-9'], char['0-9'], char['0-9'], r')']
    ]
    separator: Sep
    central_office: sequence[char['2-9'], char['0-9'], char['0-9']]
    line_number: repeat[char['0-9'], exactly[4]]
    extension: optional[sequence[ExtMarker, optional[char[' ']], repeat[char['0-9'], at_most[5]]]]


class InternationalPhone(Rule):
    optional[r'+']
    country: optional[sequence[char['1-9'], repeat[char['0-9'], at_most[2]]]]
    separator: Sep
    area_code: either[
        sequence[char['1-9'], repeat[char['0-9'], at_most[2]]],
        sequence[r'(', char['1-9'], repeat[char['0-9'], at_most[2]], r')']
    ]
    separator: Sep
    central_office: sequence[char['2-9'], char['0-9'], char['0-9']]
    separator: Sep
    line_number: repeat[char['0-9'], exactly[4]]
    extension: optional[sequence[ExtMarker, optional[char[' ']], repeat[char['0-9'], at_most[5]]]]


