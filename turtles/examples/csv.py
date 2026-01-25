"""
CSV grammar as defined by RFC 4180.
Supports all CSV features: quoted fields, unquoted fields, empty fields, multiple record separators, etc.

TODO: improve this grammar. a compelling example would be reading in a CSV and converting it to a pandas dataframe.
"""
from __future__ import annotations


from turtles import Rule, char, repeat, at_least, optional, separator, either

# --- Bytes / misc ---
class BOM(Rule):
    "\ufeff"  # UTF-8 BOM if present


# --- Record separators (accept CRLF, LF, or CR) ---
class CRLF(Rule):
    "\r\n"

class LF(Rule):
    "\n"

class CR(Rule):
    "\r"

RecordSep = CRLF | LF | CR
RecordSep.longest_match = True

# --- Delimiter (default comma) ---
class Delim(Rule):
    ","


# Optional: allow whitespace after delimiter before *next field*
# This mimics a common "skipinitialspace" behavior.
class DelimSkipInitialSpace(Rule):
    ","
    repeat[char['\x20\x09']]  # swallow spaces (0x20) and tabs (0x09) after delimiter


# --- Quoting ---
class EscapedQuote(Rule):
    '""'  # doubled quote inside a quoted field


# Any char except a double quote. Includes CR/LF, commas, etc.
# (that’s what allows multiline quoted fields)
class QuotedChar(Rule):
    ch: char["\x00-\x21\x23-\U0010FFFF"]  # noqa


class QuotedField(Rule):
    '"'
    content: QuotedFieldContent
    '"'
# QuotedField.longest_match = True

class QuotedFieldContent(Rule, str):
    repeat[EscapedQuote | QuotedChar]
# QuotedFieldContent.longest_match = True


# --- Unquoted fields ---
# Typical CSV: unquoted fields end at delimiter or record separator.
# Also disallow raw quotes in unquoted fields (common strict-ish behavior).
# 
# UnquotedChar matches any character except: comma, newline, CR, and quote.
# This ensures the field naturally stops at delimiters and record separators.
class UnquotedChar(Rule):
    ch: char[
        "\x00-\x09"         # include tabs and control chars except LF/CR       # noqa
        "\x0B-\x0C"
        "\x0E-\x21"         # up to '!' (0x21), excludes '"'(0x22)
        "\x23-\x2B"         # '#'..'+'
        "\x2D-\U0010FFFF"   # '-'..unicode max (excludes ',' 0x2C)
    ]


# UnquotedField: one or more UnquotedChar characters.
# This will naturally stop when it encounters a comma, newline, CR, or quote
# because UnquotedChar excludes those characters.
# Note: we require at_least[1] so that truly empty fields return None from optional[Field]
class UnquotedField(Rule, str):
    value: repeat[UnquotedChar, at_least[1]]
# UnquotedField.longest_match = True

Field = QuotedField | UnquotedField | None

# class Field(Rule):
#     value: either[QuotedField, UnquotedField, None]


# --- Records (this is the key part to support empty fields cleanly) ---
# record := [field] (delim [field])*
#
# That means:
#   ""         -> one empty unquoted field (Field present but length 0)
#   ,a,        -> first optional[Field] is missing => leading empty field
#                then ",a" then "," with missing field => trailing empty
#
# We structure this as: first field (optional), then zero or more delimiter+field pairs
class Record(Rule):
    fields: repeat[Field, separator[Delim]]



# --- Top-level file ---
# Structured so separators are required between records, making the grammar unambiguous.
# First record has no leading separator; subsequent records require a separator before them.
# This prevents trailing newlines from creating spurious empty records.


class CSV(Rule):
    optional[BOM]
    records: repeat[Record, separator[RecordSep]]
    optional[RecordSep]  # trailing separator


# Variant that allows spaces/tabs after commas (like skipinitialspace):
class RecordSkipInitialSpace(Rule):
    fields: repeat[Field, separator[DelimSkipInitialSpace]]


class CSVSkipInitialSpace(Rule):
    optional[BOM]
    records: repeat[RecordSkipInitialSpace, separator[RecordSep]]
    optional[RecordSep]  # trailing separator