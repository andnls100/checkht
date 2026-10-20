# -*- coding: utf-8 -*-
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import contract_ai as c


class FakeResponse:
    status_code = 200
    headers = {}
    ok = True
    reason = "OK"
    encoding = "utf-8"

    def __init__(self, data):
        self._data = data
        self.text = json.dumps(data, ensure_ascii=False)

    def json(self):
        return self._data


def reply(content=None, reasoning=None, finish="stop"):
    message = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    return {"id": "x", "choices": [{"index": 0, "finish_reason": finish, "message": message}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}


def gateway():
    gw = c.AIGateway.__new__(c.AIGateway)
    gw.get_api_key = lambda provider: "k"
    gw.build_chat_url = lambda provider: "http://x/v1/chat/completions"
    return gw


def call(data, provider=None):
    provider = {"name": "p", "model": "m", **(provider or {})}
    sent = []

    def fake_post(url, headers=None, json=None, timeout=None, **kw):
        sent.append(json)
        return FakeResponse(data)

    with mock.patch.object(c.requests, "post", side_effect=fake_post), contextlib.redirect_stdout(io.StringIO()):
        try:
            return gateway().request_sync(provider, "prompt"), sent[0]
        except RuntimeError as exc:
            return exc, sent[0]


JSON3 = '{"a": {"value": null}, "b": {"value": "x"}, "c": {"value": "}{"}}'


class Gateway(unittest.TestCase):
    def test_default_max_tokens_is_at_least_20000(self):
        _, body = call(reply('{"a": 1}'))
        self.assertGreaterEqual(body["max_tokens"], 20000)

    def test_configured_max_tokens_and_extra_body_are_sent(self):
        _, body = call(reply('{"a": 1}'), {"max_tokens": 30000, "extra_body": {"thinking": {"type": "disabled"}}})
        self.assertEqual(body["max_tokens"], 30000)
        self.assertEqual(body["thinking"], {"type": "disabled"})

    def test_empty_content_cut_off_by_length_gives_a_clear_error(self):
        result, _ = call(reply("", reasoning="Let me think... still thinking", finish="length"))
        self.assertIsInstance(result, RuntimeError)
        self.assertIn("被截断", str(result))
        self.assertIn("extra_body", str(result))

    def test_json_inside_reasoning_is_salvaged_when_content_is_empty(self):
        result, _ = call(reply("", reasoning="thinking...\nfinal: " + JSON3, finish="stop"))
        self.assertEqual(json.loads(result)["b"], {"value": "x"})

    def test_truncated_json_with_content_is_reported(self):
        result, _ = call(reply('{"a": {"value": "x"', finish="length"))
        self.assertIsInstance(result, RuntimeError)
        self.assertIn("被截断", str(result))

    def test_normal_reply(self):
        result, _ = call(reply('{"a": 1}', reasoning="thoughts"))
        self.assertEqual(result, '{"a": 1}')

    def test_extract_last_json_object(self):
        self.assertEqual(json.loads(c.extract_last_json_object("x " + JSON3 + " y"))["a"], {"value": None})
        self.assertIsNone(c.extract_last_json_object('{"only": 1}'))
        self.assertIsNone(c.extract_last_json_object(None))


if __name__ == "__main__":
    unittest.main()
