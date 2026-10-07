import base64
import os
import unittest
from unittest.mock import patch

import app as travel_app


class GenerateAudioGuideTests(unittest.TestCase):
    def setUp(self):
        travel_app.app.config["TESTING"] = True
        self.client = travel_app.app.test_client()
        self.request_data = {
            "place": "Taj Mahal",
            "answerType": "Summary",
            "language": "English",
            "voiceId": "Matthew",
            "locale": "en-US",
        }

    def test_rejects_unsupported_voice_without_calling_providers(self):
        self.request_data["voiceId"] = "Not an English voice"
        with patch.object(travel_app, "generate_description") as generate:
            response = self.client.post(
                "/generate-audio-guide",
                json=self.request_data,
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("voice", response.get_json()["error"])
        generate.assert_not_called()

    def test_rejects_non_string_choices(self):
        for field in ("answerType", "language"):
            with self.subTest(field=field):
                request_data = dict(self.request_data)
                request_data[field] = ["invalid"]
                response = self.client.post(
                    "/generate-audio-guide",
                    json=request_data,
                )
                self.assertEqual(response.status_code, 400)

    def test_requires_both_provider_keys(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.post(
                "/generate-audio-guide",
                json=self.request_data,
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("API keys", response.get_json()["error"])

    def test_generates_description_and_base64_audio(self):
        audio_bytes = b"sample-mp3"
        with (
            patch.dict(
                os.environ,
                {"GEMINI_API_KEY": "test-key", "MURF_AI_API_KEY": "test-key"},
            ),
            patch.object(
                travel_app,
                "generate_description",
                return_value="A guide to the Taj Mahal.",
            ) as generate_description,
            patch.object(
                travel_app,
                "generate_speech",
                return_value=audio_bytes,
            ) as generate_speech,
        ):
            response = self.client.post(
                "/generate-audio-guide",
                json=self.request_data,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "description": "A guide to the Taj Mahal.",
                "audioBase64": base64.b64encode(audio_bytes).decode("ascii"),
            },
        )
        generate_description.assert_called_once_with("Taj Mahal", "Summary", "English")
        generate_speech.assert_called_once_with(
            "A guide to the Taj Mahal.",
            "Matthew",
            "en-US",
        )

    def test_reports_temporary_gemini_overload_as_retryable(self):
        error = travel_app.APIError(
            503,
            {
                "error": {
                    "code": 503,
                    "message": "The model is temporarily unavailable.",
                    "status": "UNAVAILABLE",
                }
            },
        )
        with (
            patch.dict(
                os.environ,
                {"GEMINI_API_KEY": "test-key", "MURF_AI_API_KEY": "test-key"},
            ),
            patch.object(travel_app, "generate_description", side_effect=error),
            patch.object(travel_app, "generate_speech") as generate_speech,
        ):
            response = self.client.post(
                "/generate-audio-guide",
                json=self.request_data,
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("temporarily busy", response.get_json()["error"])
        generate_speech.assert_not_called()


if __name__ == "__main__":
    unittest.main()
