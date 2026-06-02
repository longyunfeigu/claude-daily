# input: _lib_schema module, JSON Schema dict, Python dict instance
# output: unittest test results for validate() function
# owner: wanhua.gu
# pos: skill test suite - validates JSON Schema validator; 一旦我被更新，务必更新我的开头注释以及所属文件夹的md
import unittest

import _lib_schema as sv


class SchemaValidatorTest(unittest.TestCase):
    def setUp(self):
        self.daily = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["member_id", "type", "content"],
            "additionalProperties": False,
            "properties": {
                "member_id": {"type": "string", "pattern": "^[a-z]+$"},
                "type":      {"type": "string", "enum": ["personal", "boss"]},
                "content":   {"type": "string", "minLength": 1},
                "duration":  {"type": "integer", "minimum": 0},
            },
        }

    def test_valid_payload_passes(self):
        errors = sv.validate({"member_id": "wanhua", "type": "personal", "content": "x"}, self.daily)
        self.assertEqual([], errors)

    def test_missing_required_field(self):
        errors = sv.validate({"type": "personal", "content": "x"}, self.daily)
        self.assertTrue(any("member_id" in e for e in errors))

    def test_wrong_type_for_string_field(self):
        errors = sv.validate({"member_id": 123, "type": "personal", "content": "x"}, self.daily)
        self.assertTrue(any("member_id" in e for e in errors))

    def test_enum_violation(self):
        errors = sv.validate({"member_id": "wanhua", "type": "good", "content": "x"}, self.daily)
        self.assertTrue(any("type" in e for e in errors))

    def test_pattern_violation(self):
        errors = sv.validate({"member_id": "WANHUA", "type": "personal", "content": "x"}, self.daily)
        self.assertTrue(any("member_id" in e for e in errors))

    def test_min_length_violation(self):
        errors = sv.validate({"member_id": "wanhua", "type": "personal", "content": ""}, self.daily)
        self.assertTrue(any("content" in e for e in errors))

    def test_additional_properties_forbidden(self):
        errors = sv.validate({"member_id": "wanhua", "type": "personal", "content": "x", "unknown": "field"}, self.daily)
        self.assertTrue(any("unknown" in e for e in errors))

    def test_optional_field_omitted_passes(self):
        errors = sv.validate({"member_id": "wanhua", "type": "personal", "content": "x"}, self.daily)
        self.assertEqual([], errors)

    def test_minimum_violation_on_integer(self):
        errors = sv.validate({"member_id": "wanhua", "type": "personal", "content": "x", "duration": -1}, self.daily)
        self.assertTrue(any("duration" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
