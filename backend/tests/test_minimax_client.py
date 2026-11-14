import os
import unittest
from unittest.mock import Mock, patch

from app.services import minimax_client


class GroqClientTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()

    def tearDown(self):
        self.environment.stop()

    def test_groq_is_the_default_provider(self):
        os.environ["GROQ_API_KEY"] = "test-key"

        self.assertTrue(minimax_client.is_configured())
        self.assertEqual(minimax_client.provider_name(), "groq")
        self.assertEqual(
            minimax_client._api_url(),
            "https://api.groq.com/openai/v1/chat/completions",
        )
        self.assertEqual(minimax_client._model(), "llama-3.3-70b-versatile")

    @patch("app.services.minimax_client.requests.post")
    def test_chat_sends_groq_bearer_auth_and_json_mode(self, post):
        os.environ.update({
            "GROQ_API_KEY": "test-key",
            "AI_PROVIDER": "groq",
        })
        post.return_value = Mock(
            json=lambda: {"choices": [{"message": {"content": '{"ok": true}'}}]},
        )

        result = minimax_client.chat(
            [{"role": "user", "content": "Return JSON"}],
            json_mode=True,
        )

        self.assertEqual(result, '{"ok": true}')
        self.assertEqual(post.call_args.args[0], minimax_client.DEFAULT_API_URL)
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(
            post.call_args.kwargs["json"]["response_format"],
            {"type": "json_object"},
        )

    def test_generic_and_legacy_configuration_remain_supported(self):
        os.environ["AI_API_KEY"] = "generic-key"
        self.assertTrue(minimax_client.is_configured())
        self.assertEqual(minimax_client._api_key(), "generic-key")

        os.environ.clear()
        os.environ["MINIMAX_API_KEY"] = "legacy-key"
        self.assertTrue(minimax_client.is_configured())
        self.assertEqual(minimax_client._api_key(), "legacy-key")


if __name__ == "__main__":
    unittest.main()
