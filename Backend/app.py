import base64
import logging
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from google import genai
from google.genai.errors import APIError

PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIRECTORY / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FRONTEND_DIRECTORY = PROJECT_DIRECTORY / "Frontend"
app = Flask(__name__, static_folder=str(FRONTEND_DIRECTORY), static_url_path="")
app.config["JSON_SORT_KEYS"] = False

LANGUAGES = {
    "English": {"locale": "en-US", "voices": {"Male": "Matthew", "Female": "Alicia"}},
    "Hindi": {"locale": "hi-IN", "voices": {"Male": "Aman", "Female": "Namrita"}},
    "Tamil": {"locale": "ta-IN", "voices": {"Male": "Murali", "Female": "Iniya"}},
    "Telugu": {"locale": "te-IN", "voices": {"Male": "Zion", "Female": "Josie"}},
}

PROMPTS = {
    "Summary": (
        'You are a professional tourist guide. Give an engaging, accessible '
        'overview of "{place}" in {language}. Explain its historical significance, '
        'why it is famous, and its key architectural or cultural highlights. '
        'Avoid excessive dates and keep it to around 200 words. Respond only in {language}.'
    ),
    "Detailed": (
        'You are a professional tourist guide. Give an immersive explanation of '
        '"{place}" in {language}, covering its historical background, architecture, '
        'cultural importance, notable events, interesting facts, and useful visitor '
        'insights. Tell it as a clear story and keep it to around 400 words. '
        'Respond only in {language}.'
    ),
}

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
MURF_SPEECH_URL = "https://global.api.murf.ai/v1/speech/stream"


class ConfigurationError(Exception):
    """Raised when a required service credential is not configured."""


def generate_description(place: str, answer_type: str, language: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ConfigurationError("GEMINI_API_KEY is not configured.")

    client = genai.Client(api_key=api_key)
    prompt = PROMPTS[answer_type].format(place=place, language=language)
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )
            break
        except APIError as error:
            if error.code != 503 or attempt == 2:
                raise
            time.sleep(attempt + 1)

    try:
        description = (response.text or "").strip()
    except ValueError as error:
        raise RuntimeError("Gemini did not return text.") from error
    if not description:
        raise RuntimeError("Gemini returned an empty guide.")
    return description


def generate_speech(text: str, voice_id: str, locale: str) -> bytes:
    api_key = os.getenv("MURF_AI_API_KEY")
    if not api_key:
        raise ConfigurationError("MURF_AI_API_KEY is not configured.")

    response = requests.post(
        MURF_SPEECH_URL,
        headers={"api-key": api_key, "Content-Type": "application/json"},
        json={
            "voice_id": voice_id,
            "text": text,
            "locale": locale,
            "model": "FALCON",
            "format": "MP3",
            "sampleRate": 24000,
            "channelType": "MONO",
        },
        timeout=(10, 120),
    )
    response.raise_for_status()
    if not response.content:
        raise RuntimeError("Murf returned an empty audio response.")
    return response.content


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/health")
def health_check():
    return jsonify({"status": "ok", "service": "travel-guide"})


@app.post("/generate-audio-guide")
def generate_audio_guide():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send a JSON request body."}), 400

    place = data.get("place")
    answer_type = data.get("answerType")
    language = data.get("language")
    voice_id = data.get("voiceId")

    if not isinstance(place, str) or not place.strip() or len(place.strip()) > 120:
        return jsonify({"error": "Place must be between 1 and 120 characters."}), 400
    if not isinstance(answer_type, str) or answer_type not in PROMPTS:
        return jsonify({"error": "answerType must be Summary or Detailed."}), 400
    if not isinstance(language, str) or language not in LANGUAGES:
        return jsonify({"error": "Choose a supported language."}), 400

    language_settings = LANGUAGES[language]
    if voice_id not in language_settings["voices"].values():
        return jsonify({"error": "Choose a voice that matches the selected language."}), 400
    if not os.getenv("GEMINI_API_KEY") or not os.getenv("MURF_AI_API_KEY"):
        return jsonify({"error": "Configure both Gemini and Murf API keys to generate a guide."}), 503

    try:
        description = generate_description(place.strip(), answer_type, language)
        audio_bytes = generate_speech(
            description,
            voice_id,
            language_settings["locale"],
        )
    except ConfigurationError as error:
        logger.error("%s", error)
        return jsonify({"error": "Configure both Gemini and Murf API keys to generate a guide."}), 503
    except APIError as error:
        logger.exception("Gemini guide generation failed.")
        if error.code == 503:
            return jsonify(
                {"error": "Gemini is temporarily busy. Please try again shortly."}
            ), 503
        return jsonify({"error": "Gemini could not generate the guide. Please try again."}), 502
    except requests.RequestException:
        logger.exception("Murf audio generation failed.")
        return jsonify({"error": "Murf could not generate audio. Please try again."}), 502
    except RuntimeError:
        logger.exception("A guide provider returned an invalid response.")
        return jsonify({"error": "A guide provider returned an empty response. Please try again."}), 502

    return jsonify(
        {
            "description": description,
            "audioBase64": base64.b64encode(audio_bytes).decode("ascii"),
        }
    )


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    app.run(
        host=host,
        port=port,
        debug=os.getenv("FLASK_DEBUG", "").lower() == "true",
    )
