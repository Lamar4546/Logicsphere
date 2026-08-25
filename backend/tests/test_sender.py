import os
import unittest
from unittest.mock import Mock, patch

from app.notifications.sender import send_email, send_sms, send_whatsapp


class SenderTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()

    def tearDown(self):
        self.environment.stop()

    def test_missing_credentials_returns_normalized_failure(self):
        for sender, args, provider in (
            (send_sms, ("+15550000000", "Update"), "twilio"),
            (send_whatsapp, ("+15550000000", "Update"), "twilio_whatsapp"),
            (send_email, ("test@example.com", "Update", "Body"), "sendgrid"),
        ):
            result = sender(*args)
            self.assertEqual(set(result), {"success", "provider", "message_id", "error"})
            self.assertFalse(result["success"])
            self.assertEqual(result["provider"], provider)

    @patch("app.notifications.sender.requests.post")
    def test_sms_returns_provider_message_id(self, post):
        os.environ.update({"TWILIO_ACCOUNT_SID": "ACtest", "TWILIO_AUTH_TOKEN": "secret", "TWILIO_SMS_FROM": "+15551111111"})
        post.return_value = Mock(ok=True, json=lambda: {"sid": "SM123"})
        result = send_sms("+15552222222", "On the way")
        self.assertEqual(result, {"success": True, "provider": "twilio", "message_id": "SM123", "error": None})

    @patch("app.notifications.sender.requests.post")
    def test_email_uses_sandbox_mode_by_default(self, post):
        os.environ.update({"SENDGRID_API_KEY": "SG.test", "SENDGRID_FROM_EMAIL": "demo@example.com"})
        post.return_value = Mock(status_code=202, headers={"X-Message-Id": "mail-123"})
        result = send_email("customer@example.com", "ETA update", "Body")
        self.assertTrue(result["success"])
        self.assertTrue(post.call_args.kwargs["json"]["mail_settings"]["sandbox_mode"]["enable"])


if __name__ == "__main__":
    unittest.main()
