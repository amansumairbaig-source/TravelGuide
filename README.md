# AI Travel Guide

Generate an AI-written travel narration with Gemini and listen to it using
Murf's Falcon text-to-speech API. The browser talks to Flask, so provider keys
stay on the server.

## Run locally

1. Install Python dependencies from the project directory:

   ```powershell
   python -m pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and add your Gemini and Murf API keys.
3. Start the application:

   ```powershell
   python Backend\app.py
   ```

4. Open <http://127.0.0.1:5000>.

The app supports the featured destinations shown in the page, Summary or
Detailed scripts, and English, Hindi, Tamil, or Telugu narration. `GEMINI_MODEL`
can optionally be set in `.env` to choose another model available to your
Gemini API key. API keys are never sent to the browser.

## Production deployment

This project is ready to run behind a production WSGI server such as Gunicorn.
The app binds to `HOST` and `PORT` environment variables and exposes a health
check at `/health` for deployment monitoring.

Recommended production command:

```bash
gunicorn --bind 0.0.0.0:$PORT Backend.app:app
```

### Render deployment

This repository includes a `render.yaml` file for a one-click Render setup.
After pushing the project to GitHub, create a new Web Service on Render and choose
this repository. Render will install dependencies from `requirements.txt` and start the app with Gunicorn.

Set these environment variables in the Render dashboard:

- `GEMINI_API_KEY`
- `MURF_AI_API_KEY`
- `GEMINI_MODEL` (optional, defaults to `gemini-3.1-flash-lite`)
- `HOST=0.0.0.0`

Render automatically provides `PORT`, so you do not need to set it manually.

The included `Procfile` is configured for Heroku-style deployments. For containerized deployments, the project also includes a `Dockerfile` that runs the app with Gunicorn on Linux.

## API

`POST /generate-audio-guide` accepts JSON containing `place`, `answerType`,
`language`, and `voiceId`. It returns the generated `description` and an
`audioBase64` MP3 string. The backend validates supported languages and
language/voice combinations and selects the corresponding locale itself.

Provider API keys and network access are required for guide generation.
