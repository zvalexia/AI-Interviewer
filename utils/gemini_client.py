import os
import json
from collections import Counter
import google.generativeai as genai


DEFAULT_QUESTION_COUNT = 5
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
        "communication": 0,
        "depth": 0,
        "tradeoffs": 0,
        "structure": 0,
        "overall": 0,
        "highlights": [],
        "areas_to_improve": [
            "Provide complete, substantive responses with concrete examples.",
            "Address constraints, decisions, and trade-offs in each answer.",
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
        depth = 7
    elif avg_words >= 25:
        depth = 5
    else:
        depth = 3

    structure = 7 if any(
        marker in " ".join(answers).lower() for marker in ["first", "then", "because", "therefore", "finally"]
    ) else 5
    communication = 7 if avg_words >= 30 else 5
    tradeoffs = 6 if "trade" in " ".join(answers).lower() else 3
    overall = round((communication + depth + tradeoffs + structure) / 4)

    return {
        "communication": communication,
        "depth": depth,
        "tradeoffs": tradeoffs,
        "structure": structure,
        "overall": overall,
        "highlights": [
            "Demonstrates baseline understanding of the topic.",
            "Includes some practical context in responses.",
        ],
        "areas_to_improve": [
            "Provide concrete examples with measurable outcomes.",
            "Explicitly discuss constraints, alternatives, and trade-offs.",
        ],
    }


def generate_scorecard(topic, qna_pairs):
    answers = [a for _, a in qna_pairs]
    try:
        context = "\n\n".join([f"Q: {q}\nA: {a}" for q, a in qna_pairs])
        prompt = (
            "You are a senior technical hiring evaluator producing a scorecard for a hiring committee. "
            "Return ONLY valid JSON with no extra text or markdown.\n\n"
            f"Topic: {topic}\n\n"
            "Evaluate the candidate on a 0-10 integer scale (0 = no demonstrated competence, "
            "5 = meets expectations, 8 = exceeds expectations, 10 = exceptional) for each dimension:\n\n"
            "- communication: Clarity, conciseness, and ability to articulate ideas\n"
            "- depth: Technical depth, specificity, and domain knowledge demonstrated\n"
            "- tradeoffs: Ability to reason about trade-offs, constraints, and alternatives\n"
            "- structure: Logical organization and coherent argumentation\n"
            "- overall: Holistic assessment reflecting all dimensions (not a simple average)\n\n"
            "Also provide:\n"
            "- highlights: exactly 3 specific strengths observed (short bullet strings)\n"
            "- areas_to_improve: exactly 3 actionable improvement areas (short bullet strings)\n\n"
            "Be rigorous and calibrated. A score of 5 means 'adequate'. "
            "Most candidates should score between 4-7. Reserve 8+ for genuinely strong answers "
            "with concrete examples, nuanced reasoning, and clear expertise.\n\n"
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
            parsed[key] = max(0, min(10, int(parsed[key])))

        if not isinstance(parsed["highlights"], list) or not isinstance(parsed["areas_to_improve"], list):
            raise ValueError("Highlights/improvement fields are not lists.")

        parsed["highlights"] = [str(x) for x in parsed["highlights"][:3]]
        parsed["areas_to_improve"] = [str(x) for x in parsed["areas_to_improve"][:3]]
        if len(parsed["highlights"]) < 2 or len(parsed["areas_to_improve"]) < 2:
            raise ValueError("Insufficient bullet points in scorecard response.")

        return parsed
    except Exception as e:
        print(f"Error generating scorecard: {e}")
        return _fallback_scorecard(answers)

def generate_questions(topic):
    try:
        prompt = (
            "You are a senior technical interviewer conducting a structured evaluation. "
            f"Generate exactly 5 interview questions for this topic: {topic}.\n\n"
            "Question design principles:\n"
            "1. Start with a broad context question to assess overall familiarity\n"
            "2. Progress to specific technical scenarios requiring concrete examples\n"
            "3. Include at least one question about trade-offs or design decisions\n"
            "4. Include one question that tests depth through a real-world problem\n"
            "5. End with a question about lessons learned or how they would approach something differently\n\n"
            "Questions should be open-ended, require substantive answers, and reveal the candidate's "
            "actual experience level. Avoid yes/no or trivia-style questions.\n\n"
            "Return only the questions, one per line, with no numbering, bullets, or extra text."
        )
        raw_text = _generate_text(prompt)
        questions = _sanitize_questions(raw_text, max_count=5)

        if not questions:
            raise ValueError("Empty response")
        return questions
    except Exception as e:
        print(f"Error generating questions: {e}")
        return [
            f"Walk me through your experience with {topic} and where you've applied it most significantly.",
            f"Describe a specific challenge you faced working with {topic} and how you resolved it.",
            f"What trade-offs have you had to consider when making decisions related to {topic}?",
            f"Can you walk me through a real project where {topic} played a critical role in the outcome?",
            f"Looking back, what would you do differently in your approach to {topic} and why?",
        ]


def generate_summary(topic, qna_pairs):
    try:
        context = "\n\n".join([f"Q: {q}\nA: {a}" for q, a in qna_pairs])
        prompt = (
            "You are a senior hiring evaluator writing a debrief summary for a hiring committee. "
            "Your audience is hiring managers and senior engineers who need to make a go/no-go decision.\n\n"
            f"Topic: {topic}\n\n"
            "Write the following sections using plain text (no markdown headers or formatting):\n\n"
            "EXECUTIVE SUMMARY\n"
            "A 3-4 sentence assessment of the candidate's demonstrated competence. "
            "Reference specific answers. State whether the candidate showed surface-level or deep understanding. "
            "Note the strongest and weakest areas.\n\n"
            "KEY OBSERVATIONS\n"
            "- 3-4 specific, evidence-based observations from the transcript\n"
            "- Each observation should cite what the candidate said or failed to address\n\n"
            "HIRING RECOMMENDATION\n"
            "A 1-2 sentence recommendation for the hiring team, indicating confidence level "
            "and any follow-up areas to probe in subsequent rounds.\n\n"
            "Keep the tone professional, direct, and evidence-based. Avoid generic praise. "
            "If answers were vague, say so explicitly.\n\n"
            f"Transcript:\n{context}"
        )

        return _generate_text(prompt)
    except Exception as e:
        print(f"Error generating summary: {e}")
        return (
            "Failed to generate AI summary due to an API error. "
            "Your interview responses were still saved successfully."
        )
