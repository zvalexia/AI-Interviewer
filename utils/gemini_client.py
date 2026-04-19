import os
import json
from collections import Counter
import google.generativeai as genai


DEFAULT_QUESTION_COUNT = 4
MODEL_PREFERENCES = [
    "models/gemini-2.5-flash",
    "models/gemini-2.0-flash",
    "models/gemini-flash-latest",
    "models/gemini-pro-latest",
]


def _safe_response_text(response):
    text = getattr(response, "text", "")
    return text.strip() if text else ""


def _extract_json_object(text):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model response.")
    return json.loads(text[start:end + 1])

def setup_gemini():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")
    genai.configure(api_key=api_key)


def _select_model_name():
    available = set()
    for model in genai.list_models():
        methods = set(getattr(model, "supported_generation_methods", []) or [])
        if "generateContent" in methods:
            available.add(model.name)

    for preferred in MODEL_PREFERENCES:
        if preferred in available:
            return preferred

    if available:
        return sorted(available)[0]

    raise RuntimeError("No Gemini models with generateContent support are available.")


def _generate_text(prompt):
    setup_gemini()
    model_name = _select_model_name()
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(prompt)
    text = _safe_response_text(response)
    if not text:
        raise ValueError("Gemini returned an empty response.")
    return text


def _sanitize_questions(raw_text, max_count=5):
    candidates = []
    for line in raw_text.split("\n"):
        cleaned = line.strip().lstrip("-*").strip()
        if cleaned and len(cleaned) > 5:
            candidates.append(cleaned)
    unique_questions = list(dict.fromkeys(candidates))
    return unique_questions[:max_count]


def assess_response_signal(answers):
    total_answers = len(answers)
    if total_answers == 0:
        return {
            "is_low_signal": True,
            "meaningful_answers": 0,
            "total_answers": 0,
            "avg_words": 0,
            "reason": "No answers were provided.",
        }

    meaningful_answers = 0
    total_words = 0

    for answer in answers:
        normalized = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in answer.lower())
        words = [w for w in normalized.split() if w]
        total_words += len(words)

        unique_ratio = (len(set(words)) / len(words)) if words else 0
        vowel_words = sum(1 for w in words if len(w) > 2 and any(v in w for v in "aeiou"))
        has_enough_length = len(words) >= 6
        has_variety = unique_ratio >= 0.45
        has_readable_words = vowel_words >= 2

        if has_enough_length and has_variety and has_readable_words:
            meaningful_answers += 1

    avg_words = total_words / total_answers
    is_low_signal = meaningful_answers < max(2, total_answers // 2) or avg_words < 7
    reason = (
        "Most answers were too short or non-informative to evaluate reliably."
        if is_low_signal
        else "Sufficient signal detected."
    )

    return {
        "is_low_signal": is_low_signal,
        "meaningful_answers": meaningful_answers,
        "total_answers": total_answers,
        "avg_words": round(avg_words, 1),
        "reason": reason,
    }


def build_low_signal_summary(topic, signal):
    return (
        f"The interview on '{topic}' does not contain enough meaningful response content to produce a reliable AI evaluation. "
        f"Only {signal['meaningful_answers']} out of {signal['total_answers']} answers had sufficient signal.\n\n"
        "Please retry with specific answers that include examples, decisions, and trade-offs."
    )


def build_low_signal_scorecard():
    return {
        "communication": 1,
        "depth": 1,
        "tradeoffs": 1,
        "structure": 1,
        "overall": 1,
        "highlights": [],
        "areas_to_improve": [
            "Use complete sentences with concrete examples.",
            "Explain constraints, decisions, and trade-offs in each answer.",
        ],
    }


def extract_basic_analysis(answers):
    positive_words = {
        "good", "great", "strong", "improve", "improved", "success", "successful",
        "effective", "clear", "confident", "learned", "growth", "scalable", "reliable"
    }
    negative_words = {
        "hard", "difficult", "issue", "issues", "problem", "problems", "weak",
        "confusing", "failed", "failure", "slow", "unclear", "risk"
    }

    token_counter = Counter()
    pos = 0
    neg = 0

    for answer in answers:
        tokens = [
            token.strip(".,!?;:()[]{}\"'").lower()
            for token in answer.split()
            if token.strip()
        ]
        token_counter.update(token for token in tokens if len(token) > 3)
        pos += sum(1 for token in tokens if token in positive_words)
        neg += sum(1 for token in tokens if token in negative_words)

    top_keywords = [word for word, _ in token_counter.most_common(6)]
    if pos > neg:
        sentiment = "Mostly positive/confident"
    elif neg > pos:
        sentiment = "Mostly challenge-focused"
    else:
        sentiment = "Mixed or neutral"

    return {
        "sentiment": sentiment,
        "keywords": top_keywords,
    }


def _fallback_scorecard(answers):
    word_counts = [len(a.split()) for a in answers]
    avg_words = sum(word_counts) / len(word_counts) if word_counts else 0

    if avg_words >= 45:
        depth = 4
    elif avg_words >= 25:
        depth = 3
    else:
        depth = 2

    structure = 4 if any(
        marker in " ".join(answers).lower() for marker in ["first", "then", "because", "therefore", "finally"]
    ) else 3
    communication = 4 if avg_words >= 30 else 3
    tradeoffs = 4 if "trade" in " ".join(answers).lower() else 2
    overall = round((communication + depth + tradeoffs + structure) / 4)

    return {
        "communication": communication,
        "depth": depth,
        "tradeoffs": tradeoffs,
        "structure": structure,
        "overall": overall,
        "highlights": [
            "Clear baseline understanding of the topic.",
            "Some practical context included in responses.",
        ],
        "areas_to_improve": [
            "Use more concrete examples and measurable outcomes.",
            "Explicitly discuss constraints and trade-offs.",
        ],
    }


def generate_scorecard(topic, qna_pairs):
    answers = [a for _, a in qna_pairs]
    try:
        context = "\n\n".join([f"Q: {q}\nA: {a}" for q, a in qna_pairs])
        prompt = (
            "You are an interview evaluator. Return ONLY valid JSON.\n"
            f"Topic: {topic}\n\n"
            "Evaluate the candidate on a 1-5 scale with these keys:\n"
            "communication, depth, tradeoffs, structure, overall, highlights, areas_to_improve\n"
            "Rules:\n"
            "- Numeric keys must be integers 1-5\n"
            "- overall should reflect the other scores\n"
            "- highlights and areas_to_improve must each contain exactly 2 short bullet strings\n"
            "Return only one JSON object with those keys and no extra text.\n\n"
            f"Transcript:\n{context}"
        )
        raw = _generate_text(prompt)
        parsed = _extract_json_object(raw)

        required = [
            "communication",
            "depth",
            "tradeoffs",
            "structure",
            "overall",
            "highlights",
            "areas_to_improve",
        ]
        for key in required:
            if key not in parsed:
                raise ValueError(f"Missing scorecard key: {key}")

        for key in ["communication", "depth", "tradeoffs", "structure", "overall"]:
            parsed[key] = max(1, min(5, int(parsed[key])))

        if not isinstance(parsed["highlights"], list) or not isinstance(parsed["areas_to_improve"], list):
            raise ValueError("Highlights/improvement fields are not lists.")

        parsed["highlights"] = [str(x) for x in parsed["highlights"][:2]]
        parsed["areas_to_improve"] = [str(x) for x in parsed["areas_to_improve"][:2]]
        if len(parsed["highlights"]) < 2 or len(parsed["areas_to_improve"]) < 2:
            raise ValueError("Insufficient bullet points in scorecard response.")

        return parsed
    except Exception as e:
        print(f"Error generating scorecard: {e}")
        return _fallback_scorecard(answers)

def generate_questions(topic):
    try:
        prompt = (
            "You are an interviewer. Generate exactly 4 short, high-signal interview questions "
            f"for this topic: {topic}. "
            "Order them progressively from broad context to practical depth. "
            "Return only the questions, one per line, with no numbering or bullets."
        )
        raw_text = _generate_text(prompt)
        questions = _sanitize_questions(raw_text, max_count=5)

        if not questions:
            raise ValueError("Empty response")
        return questions
    except Exception as e:
        print(f"Error generating questions: {e}")
        return [
            f"What is your general experience with {topic}?",
            "What do you consider the biggest challenges in this area?",
            "Can you provide a specific example of applying this in a project?",
            "If you had to improve one thing in your approach, what would it be?"
        ]


def generate_summary(topic, qna_pairs):
    try:
        context = "\n\n".join([f"Q: {q}\nA: {a}" for q, a in qna_pairs])
        prompt = (
            "You are an interview evaluator.\n"
            f"Topic: {topic}\n\n"
            "Given the transcript below, produce this exact structure:\n"
            "Narrative Summary:\n"
            "<4-6 sentence cohesive assessment paragraph>\n\n"
            "Key Themes:\n"
            "- 3 concise bullets\n"
            "- 3 concise bullets\n"
            "- 3 concise bullets\n\n"
            "Keep the tone professional, specific, and evidence-based.\n\n"
            f"Transcript:\n{context}"
        )

        return _generate_text(prompt)
    except Exception as e:
        print(f"Error generating summary: {e}")
        return (
            "Failed to generate AI summary due to an API error. "
            "Your interview responses were still saved successfully."
        )
