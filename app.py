import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from dotenv import load_dotenv
from utils.gemini_client import (
    generate_questions,
    generate_summary,
    extract_basic_analysis,
    generate_scorecard,
    assess_response_signal,
    build_low_signal_summary,
    build_low_signal_scorecard,
)

# Load environment variables (e.g., GEMINI_API_KEY)
load_dotenv()

app = Flask(__name__)
# Secret key is required for Flask sessions
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-12345")

# Ensure data directory exists for storing JSON files
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        topic = request.form.get("topic")
        if not topic or not topic.strip():
            flash("Please enter a valid topic.")
            return redirect(url_for("index"))
        
        # Initialize session variables for the new interview
        session['topic'] = topic.strip()
        session['questions'] = generate_questions(session['topic'])
        session['answers'] = []
        session['current_q'] = 0
        
        return redirect(url_for("interview"))
    
    return render_template("index.html")

@app.route("/interview", methods=["GET", "POST"])
def interview():
    # Ensure active session
    if 'questions' not in session or 'topic' not in session:
        return redirect(url_for("index"))

    questions = session['questions']
    current_q = session['current_q']

    # If all questions answered, proceed to summary
    if current_q >= len(questions):
        return redirect(url_for("summary"))

    if request.method == "POST":
        answer = request.form.get("answer")
        if not answer or not answer.strip():
            flash("Please provide an answer before continuing.")
            return redirect(url_for("interview"))
        
        # Save answer and advance
        answers = session.get('answers', [])
        answers.append(answer.strip())
        session['answers'] = answers

        session['current_q'] += 1
        session.modified = True  # Required to ensure lists in session update properly
        
        return redirect(url_for("interview"))

    return render_template(
        "interview.html", 
        topic=session['topic'],
        question=questions[current_q], 
        current=current_q + 1, 
        total=len(questions)
    )

@app.route("/summary")
def summary():
    if 'questions' not in session or 'answers' not in session:
        return redirect(url_for("index"))
        
    questions = session['questions']
    answers = session['answers']
    topic = session['topic']
    
    # Prepare data
    qna_pairs = list(zip(questions, answers))
    signal = assess_response_signal(answers)
    if signal["is_low_signal"]:
        summary_text = build_low_signal_summary(topic, signal)
        scorecard = build_low_signal_scorecard()
    else:
        summary_text = generate_summary(topic, qna_pairs)
        scorecard = generate_scorecard(topic, qna_pairs)

    local_analysis = extract_basic_analysis(answers)
    
    # Save to JSON
    timestamp = datetime.now().isoformat()
    data = {
        "topic": topic,
        "questions": questions,
        "answers": answers,
        "summary": summary_text,
        "scorecard": scorecard,
        "analysis": local_analysis,
        "signal": signal,
        "timestamp": timestamp
    }
    
    filename = f"interview_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)
        
    # Clear session to allow starting a new interview safely
    session.clear()
    
    return render_template(
        "summary.html", 
        topic=topic, 
        qna_pairs=qna_pairs, 
        summary=summary_text,
        scorecard=scorecard,
        analysis=local_analysis,
        signal=signal,
        filename=filename
    )

if __name__ == "__main__":
    app.run(debug=True, port=5001)
