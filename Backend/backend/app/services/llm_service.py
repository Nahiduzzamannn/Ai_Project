"""
AI agent service: generates exam questions from chapter text.

Uses any OpenAI-compatible chat API. The default is Groq's free tier
(https://console.groq.com/keys). To use Google Gemini's free tier instead set:
    LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
    LLM_MODEL=gemini-2.5-flash
"""

import json
import os
import re

from dotenv import dotenv_values, find_dotenv
from openai import BadRequestError, OpenAI

from app.core.config import settings

VALID_TYPES = {"mcq", "true_false", "short", "broad"}

SYSTEM_PROMPT = """You are an expert teacher who writes exam questions.
You only use facts that appear in the provided chapter text.
You always reply with valid JSON and nothing else."""

USER_TEMPLATE = """Chapter: {title}

Chapter text:
\"\"\"
{context}
\"\"\"

Write exam questions from the chapter text above.
Required counts:
{counts}
Difficulty: {difficulty}
{extra}
Rules:
- "mcq": exactly 4 options in "options", "answer" must be the exact text of the correct option.
- "true_false": "options" must be ["True", "False"], "answer" is "True" or "False".
- "short": 1-3 sentence answer in "answer". "broad": a model answer of a short paragraph in "answer".
- Do not number the questions and do not put option letters like "A)" inside options.
- Default marks: mcq 1, true_false 1, short 2, broad 5.

Reply with JSON in exactly this shape:
{{"questions": [{{"qtype": "mcq", "text": "...", "options": ["...","...","...","..."], "answer": "...", "marks": 1, "difficulty": "{difficulty}"}}]}}"""


class LLMNotConfigured(RuntimeError):
    pass


def _refresh_settings_from_env():
    """Re-read the LLM settings from .env so a newly added key works without a restart."""
    values = dotenv_values(find_dotenv())
    key = values.get("LLM_API_KEY") or values.get("GROQ_API_KEY")
    if key:
        settings.LLM_API_KEY = key.strip()
    if values.get("LLM_BASE_URL"):
        settings.LLM_BASE_URL = values["LLM_BASE_URL"].strip()
    if values.get("LLM_MODEL"):
        settings.LLM_MODEL = values["LLM_MODEL"].strip()


PROVIDERS = {
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "model": "gemini-2.5-flash"},
}


def check_key(api_key: str, base_url: str) -> None:
    """Raise if the key is rejected by the provider (listing models is free)."""
    OpenAI(api_key=api_key, base_url=base_url, timeout=20, max_retries=1).models.list()


def save_llm_settings(api_key: str, provider: str) -> dict:
    """Write the key/provider into Backend/backend/.env and apply it immediately."""
    cfg = PROVIDERS[provider]
    env_path = find_dotenv() or ".env"
    values = {"LLM_API_KEY": api_key, "LLM_BASE_URL": cfg["base_url"], "LLM_MODEL": cfg["model"]}
    lines = open(env_path, encoding="utf-8").read().splitlines() if os.path.exists(env_path) else []
    out, done = [], set()
    for line in lines:
        name = line.split("=", 1)[0].strip().lstrip("#").strip()
        if name in values and "=" in line:
            if name not in done:
                out.append(f"{name}={values[name]}")
                done.add(name)
            continue
        out.append(line)
    out += [f"{k}={v}" for k, v in values.items() if k not in done]
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    settings.LLM_API_KEY = api_key
    settings.LLM_BASE_URL = cfg["base_url"]
    settings.LLM_MODEL = cfg["model"]
    return {"provider": provider, "model": cfg["model"]}


def _client() -> OpenAI:
    _refresh_settings_from_env()
    if not settings.LLM_API_KEY:
        raise LLMNotConfigured(
            "LLM_API_KEY is not set. Get a free key at https://console.groq.com/keys "
            "and add LLM_API_KEY=... to Backend/backend/.env"
        )
    return OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)


def _parse_json(raw: str) -> dict:
    raw = (raw or "").strip()
    # Strip ```json fences if the model added them
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            raise ValueError("AI response was not valid JSON")
        return json.loads(m.group(0))


def chat_json(messages: list[dict], temperature: float = 0.5) -> dict | list:
    """Send a chat to the AI agent and parse its JSON reply."""
    request = dict(
        model=settings.LLM_MODEL,
        messages=messages,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    client = _client()
    try:
        resp = client.chat.completions.create(**request)
    except BadRequestError:
        # Some models/providers don't support JSON mode; the prompt still asks for JSON
        request.pop("response_format")
        resp = client.chat.completions.create(**request)
    return _parse_json(resp.choices[0].message.content)


def clean_question(q: dict, difficulty: str) -> dict | None:
    qtype = str(q.get("qtype") or q.get("type") or "").lower().replace("-", "_").replace(" ", "_")
    if qtype in ("multiple_choice", "mcqs"):
        qtype = "mcq"
    if qtype not in VALID_TYPES:
        return None
    text = str(q.get("text") or q.get("question") or "").strip()
    if not text:
        return None
    options = q.get("options")
    if qtype == "mcq":
        if not isinstance(options, list) or len(options) < 2:
            return None
        options = [re.sub(r"^\s*[A-Da-d][\).:]\s+", "", str(o)).strip() for o in options]
    elif qtype == "true_false":
        options = ["True", "False"]
    else:
        options = None
    default_marks = {"mcq": 1, "true_false": 1, "short": 2, "broad": 5}[qtype]
    try:
        marks = float(q.get("marks") or default_marks)
    except (TypeError, ValueError):
        marks = default_marks
    return {
        "qtype": qtype,
        "text": text,
        "options": options,
        "answer": str(q.get("answer") or "").strip() or None,
        "marks": marks,
        "difficulty": str(q.get("difficulty") or difficulty).lower(),
    }


def generate_questions(
    chapter_title: str,
    context: str,
    counts: dict[str, int],
    difficulty: str = "medium",
    instructions: str | None = None,
) -> list[dict]:
    """Ask the AI agent for questions. counts maps qtype -> number wanted."""
    counts = {k: v for k, v in counts.items() if v and v > 0}
    if not counts:
        return []
    labels = {
        "mcq": "multiple choice questions (qtype \"mcq\")",
        "true_false": "true/false questions (qtype \"true_false\")",
        "short": "short answer questions (qtype \"short\")",
        "broad": "broad / descriptive questions (qtype \"broad\")",
    }
    counts_text = "\n".join(f"- {n} {labels[t]}" for t, n in counts.items())
    extra = f"Extra instructions from the teacher: {instructions}\n" if instructions else ""

    prompt = USER_TEMPLATE.format(
        title=chapter_title,
        context=context[: settings.LLM_CONTEXT_CHARS],
        counts=counts_text,
        difficulty=difficulty,
        extra=extra,
    )
    data = chat_json([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ])
    items = data.get("questions", []) if isinstance(data, dict) else data
    cleaned = [clean_question(q, difficulty) for q in items if isinstance(q, dict)]
    return [q for q in cleaned if q]
