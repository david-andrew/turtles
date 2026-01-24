from turtles import Rule, char, repeat, at_least, separator, either, optional, sequence

class SemVer(Rule):
    major: NumId
    "."
    minor: NumId
    "."
    patch: NumId
    prerelease: Prerelease|None
    build: Build|None

class Prerelease(Rule):
    "-"
    ids: repeat[Id, separator['.'], at_least[1]]

class Build(Rule):
    "+"
    ids: repeat[Id, separator['.'], at_least[1]]

class NumId(Rule):
    id: '0' | sequence[char['1-9'], repeat[char['0-9']]]

class Id(Rule):
    id: repeat[char['a-zA-Z0-9-'], at_least[1]]
