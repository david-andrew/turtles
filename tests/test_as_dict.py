from __future__ import annotations

import pytest
from pathlib import Path

from turtles import (
    Rule,
    char,
    repeat,
    at_least,
    optional,
    separator,
    clear_registry_for_file,
)
from turtles.dsl import _captured_locals
from turtles.examples.json_toy import JObject as ToyJObject, JArray as ToyJArray
from turtles.examples.semver import SemVer
from turtles.examples.json import (
    JSON as FullJSON,
    JNumber as FullJNumber,
    SimpleEscape,
    HexEscape,
)

_THIS_FILE = str(Path(__file__).resolve())


@pytest.fixture(autouse=True)
def clear_test_state():
    _captured_locals.clear()
    clear_registry_for_file(_THIS_FILE)
    yield
    _captured_locals.clear()
    clear_registry_for_file(_THIS_FILE)


def test_as_dict_nested_repeat_of_rules():
    class Word(Rule):
        text: repeat[char["a-z"], at_least[1]]  # noqa

    class Words(Rule):
        items: repeat[Word, separator[" "], at_least[1]]  # noqa

    result = Words("foo bar")
    assert result.as_dict() == {
        "items": [
            {"text": "foo"},
            {"text": "bar"},
        ]
    }


def test_as_dict_optional_present_and_absent():
    class SignedInt(Rule):
        sign: optional[char["+-"]]  # noqa
        digits: repeat[char["0-9"], at_least[1]]

    assert SignedInt("+12").as_dict() == {"sign": "+", "digits": "12"}
    assert SignedInt("12").as_dict() == {"digits": "12"}


def test_as_dict_union_with_none_present_and_absent():
    class Tag(Rule):
        "#"
        name: repeat[char["a-z"], at_least[1]]  # noqa

    class Line(Rule):
        label: repeat[char["a-z"], at_least[1]]  # noqa
        tag: Tag | None

    assert Line("hello#world").as_dict() == {"label": "hello", "tag": {"name": "world"}}
    assert Line("hello").as_dict() == {"label": "hello"}


def test_as_dict_example_json_toy_object():
    result = ToyJObject('{"a":1,"b":true,"c":null}')
    assert result.as_dict() == {
        "pairs": [
            {"key": {"value": "a"}, "value": {"value": "1"}},
            {"key": {"value": "b"}, "value": {"value": "true"}},
            {"key": {"value": "c"}, "value": "null"},
        ]
    }


def test_as_dict_example_json_toy_deep_object_and_arrays():
    result = ToyJObject(
        '{"a":[1,{"b":[true,null,{"c":"see"}]}],"d":{"e":{"f":[2,3]}}}'
    )
    assert result.as_dict() == {
        "pairs": [
            {
                "key": {"value": "a"},
                "value": {
                    "items": [
                        {"value": "1"},
                        {
                            "pairs": [
                                {
                                    "key": {"value": "b"},
                                    "value": {
                                        "items": [
                                            {"value": "true"},
                                            "null",
                                            {
                                                "pairs": [
                                                    {
                                                        "key": {"value": "c"},
                                                        "value": {"value": "see"},
                                                    }
                                                ]
                                            },
                                        ]
                                    },
                                }
                            ]
                        },
                    ]
                },
            },
            {
                "key": {"value": "d"},
                "value": {
                    "pairs": [
                        {
                            "key": {"value": "e"},
                            "value": {
                                "pairs": [
                                    {
                                        "key": {"value": "f"},
                                        "value": {"items": [{"value": "2"}, {"value": "3"}]},
                                    }
                                ]
                            },
                        }
                    ]
                },
            },
        ]
    }


def test_as_dict_example_json_toy_empty_array_and_nested_arrays():
    assert ToyJArray("[[]]").as_dict() == {"items": [{"items": []}]}


def test_as_dict_example_json_full_deep_object_all_value_kinds():
    result = FullJSON(
        r"""
        {
          "a": [1, -2.5, 3e10, -4E-2, "hi", "line\n", true, false, null, {"b": [ {"c": "d"} ] }],
          "empty": [],
          "obj": {"nested": {"k": "v"}}
        }
        """
    )
    assert result.as_dict() == {
        "value": {
            "pairs": [
                {
                    "key": {"value": ["a"]},
                    "value": {
                        "items": [
                            {"whole": {"value": "1"}},
                            {"sign": "-", "whole": {"value": "2"}, "fractional": {"value": "5"}},
                            {"whole": {"value": "3"}, "exponent": {"value": "10"}},
                            {"sign": "-", "whole": {"value": "4"}, "exponent": {"sign": "-", "value": "2"}},
                            {"value": ["hi"]},
                            {"value": [r"line\n"]},
                            {"value": "true"},
                            {"value": "false"},
                            "null",
                            {
                                "pairs": [
                                    {
                                        "key": {"value": ["b"]},
                                        "value": {
                                            "items": [
                                                {
                                                    "pairs": [
                                                        {
                                                            "key": {"value": ["c"]},
                                                            "value": {"value": ["d"]},
                                                        }
                                                    ]
                                                }
                                            ]
                                        },
                                    }
                                ]
                            },
                        ]
                    },
                },
                {"key": {"value": ["empty"]}, "value": {"items": []}},
                {
                    "key": {"value": ["obj"]},
                    "value": {
                        "pairs": [
                            {
                                "key": {"value": ["nested"]},
                                "value": {
                                    "pairs": [
                                        {"key": {"value": ["k"]}, "value": {"value": ["v"]}}
                                    ]
                                },
                            }
                        ]
                    },
                },
            ]
        }
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", {"whole": {"value": "0"}}),
        ("-0", {"sign": "-", "whole": {"value": "0"}}),
        ("12.34E-5", {"whole": {"value": "12"}, "fractional": {"value": "34"}, "exponent": {"sign": "-", "value": "5"}}),
        ("-12.34E-5", {"sign": "-", "whole": {"value": "12"}, "fractional": {"value": "34"}, "exponent": {"sign": "-", "value": "5"}}),
    ],
)
def test_as_dict_example_json_full_numbers(raw: str, expected: dict[str, object]):
    assert FullJNumber(raw).as_dict() == expected


def test_as_dict_example_json_full_escapes():
    assert SimpleEscape(r"\n").as_dict() == {"ch": r"\n"}
    assert SimpleEscape(r"\"").as_dict() == {"ch": r"\""}
    assert HexEscape(r"\u0041").as_dict() == {"ch": "0041"}


def test_as_dict_example_semver():
    result = SemVer("1.2.3-alpha.1+build.5")
    assert result.as_dict() == {
        "major": {"id": "1"},
        "minor": {"id": "2"},
        "patch": {"id": "3"},
        "prerelease": {"ids": [{"id": "alpha"}, {"id": "1"}]},
        "build": {"ids": [{"id": "build"}, {"id": "5"}]},
    }
