# AI-Interviewer Agent Instructions

This document provides specialized instructions for AI coding assistants working in this repository.

## Architecture & Tech Stack
- **Framework**: Python 3 with Flask.
- **AI Integration**: `google-generativeai` (Gemini 1.5 Flash).
- **Frontend**: Standard HTML, Jinja2 templating, and vanilla CSS.
- **Data Storage**: Local JSON files.

## Project Structure & Conventions
- **Routing**: All web routes and session state logic reside in [app.py](app.py). 
- **AI Wrapper**: All API calls to Gemini must be abstracted into [utils/gemini_client.py](utils/gemini_client.py). Do not call the Gemini SDK directly from the Flask routes.
- **UI & Styling**: Keep styles constrained to [static/style.css](static/style.css) and templates within the [templates/](templates/) directory. Avoid inline CSS.
- **Data Privacy**: Finished interview transcripts are saved incrementally to [data/](data/) in JSON format. Do not track these in version control.
- **Environment Variables**: Handled via `python-dotenv`. Ensure required keys (`GEMINI_API_KEY`, `SECRET_KEY`) from `.env.example` are gracefully checked.

## Development Workflow
- **Dependencies**: Install via `pip install -r requirements.txt` (inside the `.venv` virtual environment).
- **Run Server**: Execute `python app.py` from the root directory.

## Known Pitfalls
- Application heavily relies on the Flask session object (cookie-based). Make sure to call `session.modified = True` whenever modifying nested lists (like accumulating the answer history).
