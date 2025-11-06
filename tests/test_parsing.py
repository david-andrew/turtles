from turtles import (
    Rule, char,
    repeat, either, sequence, optional, 
    at_least, at_most, exactly, separator,
)

def test_hello():
    class MyParser(Rule):
        "Hello, "
        name: repeat[char['a-zA-Z'], at_least[1]]
        "!"

    result = MyParser('Hello, World!')
    assert result.name == 'World'  
    #TODO: overload so all rules are str by default. mixins are for converting to other types
    #      or perhaps __eq__ converts to a string? or __eq__ converts to string by default else mixin? tbd
    #      or perhaps __eq__ looks at the type of other and sees if it can convert the parse to that type for a few cases (str, Rule[...], etc.)


def test_semver():
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

    class NumId(Rule, int):
        id: either[char['0'] | sequence[char['1-9'], repeat[char['0-9']]]]

    class Id(Rule, str):
        id: repeat[char['a-zA-Z0-9-'], at_least[1]]
    

    result = SemVer('1.2.3-alpha+3.14')
    assert result.major == 1
    assert result.minor == 2
    assert result.patch == 3
    assert result.prerelease is not None
    assert result.prerelease.ids == ['alpha']
    assert result.build is not None
    assert result.build.ids == ['3', '14']



def A() -> type[int]: ...
class B[T]: ...
class C:
    def __class_getitem__(self, item: str): ...
a: B[char['a-zA-Z-']]