# AI Interviewer

A mini AI-powered interviewer web app built with Flask and Gemini.

The app conducts a short interview on any user-provided topic, asks sequential AI-generated questions, collects answers interactively, generates an AI evaluation summary, and stores the full transcript locally as JSON.

## Features

- Topic-based interview initialization
- 3-5 progressive AI-generated interview questions
- Interactive question-by-question answer flow
- Fixed interview length (no extra follow-up questions)
- Low-signal/non-informative answers are penalized in scoring
- Structured final report with:
	- AI summary
	- Rubric scorecard (communication, depth, trade-offs, structure)
	- Strengths and improvement suggestions
	- Lightweight local sentiment + keyword analysis
- Automatic transcript persistence under `data/` as JSON

## Tech Stack

- Python 3
- Flask
- google-generativeai (Gemini)
- python-dotenv
- Jinja2 templates + vanilla CSS

## Project Structure

- `app.py`: Flask routes, interview state flow, JSON persistence
- `utils/gemini_client.py`: Gemini integration, model selection, prompting, scorecard generation
- `templates/`: Jinja templates for index, interview, and summary pages
- `static/style.css`: Styling
- `data/`: Saved interview outputs

## Setup

1. Create and activate virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create environment file:

```bash
cp .env.example .env
```

4. Edit `.env` and set values:

```env
GEMINI_API_KEY="your_api_key_here"
SECRET_KEY="your_flask_secret_here"
```

5. Run the app:

```bash
python3 app.py
```

6. Open in browser:

- `http://127.0.0.1:5001`

## Assignment Requirement Mapping

1. Start interview on selected topic: implemented on the home page.
2. Generate 3-5 sequential AI questions: handled by Gemini prompt generation.
3. Collect answers interactively: one question per page step with progress bar.
4. Generate brief AI summary: produced on the summary route after final answer.
5. Store transcript + summary: written to timestamped JSON files in `data/`.
6. Bonus (basic analysis): sentiment and keyword extraction included in report.

## Notes

- The app auto-selects an available Gemini model from your account instead of hardcoding legacy model IDs.
- If API generation fails, safe fallback behavior prevents data loss and still records interview responses.