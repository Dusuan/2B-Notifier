"""Prueba del bucle del agente con un cliente Gemini falso (sin red ni cuota)."""
import os
import tempfile
import unittest
from unittest import mock

from google.genai import types

from config import config
from agent import core, tools


def _resp(part: types.Part) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))])


class FakeModels:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(list(contents))
        return self.responses.pop(0)


class TestAgentLoop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.object(config, "state_file", os.path.join(self.tmp.name, "state.json")),
            mock.patch.object(config, "gemini_api_key", "fake"),
            mock.patch.object(config, "agent_max_iterations", 3),
        ]
        for p in self.patches:
            p.start()
        core._history.clear()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _run(self, responses, message="hola"):
        fake = FakeModels(responses)
        client = mock.Mock(models=fake)
        with mock.patch.object(core, "_get_client", return_value=client):
            return core.answer(1, message), fake

    def test_tool_call_then_final_text(self):
        fc = types.Part(function_call=types.FunctionCall(name="get_profile", args={}))
        with mock.patch.object(tools, "get_profile", return_value={"player_tag": "#TEST"}) as gp:
            tools.FUNCTIONS["get_profile"] = gp
            try:
                text, fake = self._run([_resp(fc), _resp(types.Part.from_text(text="Tu tag es #TEST"))])
            finally:
                tools.FUNCTIONS["get_profile"] = tools.get_profile
        self.assertEqual(text, "Tu tag es #TEST")
        self.assertEqual(len(fake.calls), 2)
        last_part = fake.calls[1][-1].parts[0]
        self.assertEqual(last_part.function_response.name, "get_profile")
        self.assertEqual(last_part.function_response.response, {"result": {"player_tag": "#TEST"}})

    def test_iteration_cap(self):
        fc = types.Part(function_call=types.FunctionCall(name="get_profile", args={}))
        text, fake = self._run([_resp(fc)] * 5)
        self.assertEqual(len(fake.calls), 3)
        self.assertIn("máximo de pasos", text)

    def test_daily_limit(self):
        with mock.patch.object(config, "gemini_daily_limit", 0):
            text, fake = self._run([])
        self.assertEqual(fake.calls, [])
        self.assertIn("tope diario", text)

    def test_unknown_tool_returns_error(self):
        self.assertIn("error", tools.call("borrar_todo", {}))


if __name__ == "__main__":
    unittest.main()
