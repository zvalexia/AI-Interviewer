import os
import google.generativeai as genai

def setup_gemini():
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)

def generate_questions(topic):
    setup_gemini()
    try:
        model = genai.GenerativeModel('gemini-1.5-pro')
        prompt = f"Generate 3 to 5 concise interview questions about: {topic}. Return ONLY the questions, separated by newlines, with no numbering, bullets, or extra text."
        response = model.generate_content(prompt)
        # Parse the response into a list of questions
        raw_text = response.text.strip()
        questions = [q.strip() for q in raw_text.split('\n') if q.strip()]
        
        # Fallback if parsing fails or too many
        if not questions:
            raise ValueError("Empty response")
        return questions[:5]
    except Exception as e:
        print(f"Error generating questions: {e}")
        # Fallback questions on failure
        return [
            f"What is your general experience with {topic}?",
            "What do you consider the biggest challenges in this area?",
            "Can you provide a specific example of applying this in a project?"
        ]

def generate_summary(qna_pairs):
    setup_gemini()
    try:
        model = genai.GenerativeModel('gemini-1.5-pro')
        context = "\n\n".join([f"Q: {q}\nA: {a}" for q, a in qna_pairs])
        prompt = f"Summarize the following interview responses. Include key themes and main points in a concise, professional format:\n\n{context}"
        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Error generating summary: {e}")
        return "Failed to generate summary due to an API error. However, your responses have been successfully recorded."
