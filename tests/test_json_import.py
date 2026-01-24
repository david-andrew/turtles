"""Test that JSON grammar can be imported and used from a different file."""
import pytest
from turtles.examples.json import JSON, JObject, JArray, JString, JNumber


class TestJSONImport:
    """Test importing and using JSON grammar from examples."""
    
    def test_basic_object(self):
        result = JSON('{"a": 1}')
        assert type(result.value).__name__ == 'JObject'
        assert len(result.value.pairs) == 1
    
    def test_array(self):
        arr = JSON('[1, 2, 3]')
        assert len(arr.value.items) == 3
    
    def test_nested_object(self):
        nested = JSON('{"nested": {"deep": [1, 2, 3]}}')
        assert len(nested.value.pairs) == 1
        inner = nested.value.pairs[0].value
        assert type(inner).__name__ == 'JObject'
        inner_array = inner.pairs[0].value
        assert type(inner_array).__name__ == 'JArray'
        assert len(inner_array.items) == 3
    
    def test_deeply_nested(self):
        """Test 5 levels of nesting."""
        deep = JSON('''
        {
          "level1": {
            "level2": {
              "level3": {
                "level4": [
                  {"level5": "deep value"}
                ]
              }
            }
          }
        }
        ''')
        # Navigate through 5 levels
        level1 = deep.value.pairs[0].value
        level2 = level1.pairs[0].value
        level3 = level2.pairs[0].value
        level4 = level3.pairs[0].value  # array
        level5 = level4.items[0]  # object in array
        # Note: JString.value is a list because repeat contains char | Escape (a Rule)
        key_value = level5.pairs[0].key.value
        assert key_value == ['level5'] or key_value == 'level5'
    
    def test_very_deeply_nested_arrays(self):
        """Test deeply nested arrays."""
        deep = JSON('[[[[[[1]]]]]]')
        # 6 levels of array nesting
        val = deep.value
        for _ in range(5):
            assert type(val).__name__ == 'JArray'
            val = val.items[0]
        assert val.items[0].whole.value == '1'
    
    def test_mixed_deep_nesting(self):
        """Test complex mixed nesting."""
        complex_json = JSON('''
        {
            "users": [
                {
                    "name": "Alice",
                    "addresses": [
                        {"city": "NYC", "zip": 10001}
                    ]
                },
                {
                    "name": "Bob",
                    "addresses": [
                        {"city": "LA", "zip": 90001},
                        {"city": "SF", "zip": 94102}
                    ]
                }
            ]
        }
        ''')
        users = complex_json.value.pairs[0].value.items
        assert len(users) == 2
        
        alice = users[0]
        # JString.value is a list because repeat contains char | Escape (a Rule)
        alice_name = alice.pairs[0].value.value
        assert alice_name == ['Alice'] or alice_name == 'Alice'
        
        bob = users[1]
        assert len(bob.pairs[1].value.items) == 2  # Bob has 2 addresses


class TestJSONComposition:
    """Test composing new rules from imported JSON rules."""
    
    @pytest.mark.skip(reason="Cross-file rule composition not yet supported")
    def test_jsonl_parsing(self):
        """Test JSONL (JSON Lines) format using imported JSON.
        
        NOTE: This test is skipped because composing rules across files
        requires combining grammars from multiple source files, which
        is not yet implemented.
        """
        from turtles import Rule, repeat, separator
        from turtles.examples.json import JSON
        
        class JSONL(Rule):
            lines: repeat[JSON, separator['\n']]
        
        jsonl_input = '{"a": 1}\n{"b": 2}\n{"c": 3}'
        result = JSONL(jsonl_input)
        
        assert len(result.lines) == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
