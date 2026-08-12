"""
Tests for _parse_json_block — the one piece of this chain that's a pure
function and doesn't require hitting the API. Run with: pytest
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.prd_chain import _parse_json_block


def test_plain_json():
    assert _parse_json_block('{"a": 1}') == {"a": 1}


def test_fenced_with_language_tag():
    text = '```json\n{"a": 1}\n```'
    assert _parse_json_block(text) == {"a": 1}


def test_fenced_without_language_tag():
    text = '```\n{"a": 1}\n```'
    assert _parse_json_block(text) == {"a": 1}


def test_stray_prose_before_and_after():
    text = 'Sure, here is the JSON:\n{"a": 1}\nLet me know if you need more.'
    assert _parse_json_block(text) == {"a": 1}


def test_nested_object():
    payload = {"a": 1, "b": {"c": [1, 2, 3]}}
    text = f"```json\n{json.dumps(payload)}\n```"
    assert _parse_json_block(text) == payload


def test_invalid_json_raises():
    import pytest
    with pytest.raises(json.JSONDecodeError):
        _parse_json_block("not json at all, no braces")
