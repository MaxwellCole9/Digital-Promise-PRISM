import os
import threading
import time
from openai import OpenAI
from prism.status import log_gpt_call
import json

GPT_KEY = os.getenv("GPT_KEY")
GPT_MODEL = os.getenv("GPT_MODEL")

if not GPT_KEY:
    raise EnvironmentError("GPT_KEY not set in environment.")

client = OpenAI(api_key=GPT_KEY)

_RATE_LIMIT_LOCK = threading.Lock()
_LAST_CALL_TIME = 0.0
_DEFAULT_MIN_REQUEST_INTERVAL = 0.15
# Setting OPENAI_MIN_REQUEST_INTERVAL=0 disables the limiter entirely.
_MIN_REQUEST_INTERVAL = max(
    0.0,
    float(os.getenv("OPENAI_MIN_REQUEST_INTERVAL", str(_DEFAULT_MIN_REQUEST_INTERVAL))),
)


def _respect_rate_limit():
    """Serialize OpenAI calls with a gentle minimum interval between requests.

    The check is thread-safe and only sleeps when a prior call finished less
    than the configured interval ago, so concurrent workers simply queue
    briefly rather than permanently blocking the pipeline.
    """

    delay = 0.0
    global _LAST_CALL_TIME
    with _RATE_LIMIT_LOCK:
        now = time.monotonic()
        elapsed = now - _LAST_CALL_TIME
        if elapsed < _MIN_REQUEST_INTERVAL:
            delay = _MIN_REQUEST_INTERVAL - elapsed
        if delay == 0:
            _LAST_CALL_TIME = now
            return

    if delay > 0:
        time.sleep(delay)

    with _RATE_LIMIT_LOCK:
        _LAST_CALL_TIME = time.monotonic()


# -----------------------------------------------------------
# get_llm_response
# Sends text and a formatted prompt to the OpenAI API and returns the response.
# IN: text (str), prompt (str), model (str), label (str or None), context_scope (str or None),
#     record_id (str or None), json_mode (bool), prompt_vars (dict or None)
# OUT: dict or str depending on json_mode
# -----------------------------------------------------------
def get_llm_response(
    text,
    prompt,
    model=GPT_MODEL,
    label=None,
    context_scope=None,
    record_id=None,
    json_mode=False,
    prompt_vars=None,
):
    if not prompt or not text:
        raise ValueError(
            "get_llm_response requires both 'prompt' and 'text' arguments."
        )

    if prompt_vars is None:
        prompt_vars = {"paper_text": text}
    else:
        prompt_vars = {**prompt_vars, "paper_text": text}

    try:
        combined_prompt = prompt.format(**prompt_vars)
    except KeyError as e:
        raise ValueError(
            f"Prompt variable {e} not provided to get_llm_response. "
            f"Template: {prompt!r} | Vars: {prompt_vars}"
        )

    kwargs = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an academic assistant generating high-quality, publication-style summary statements of research outcomes."
                ),
            },
            {"role": "user", "content": combined_prompt},
        ],
        "temperature": 0,
        "max_tokens": 350,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        _respect_rate_limit()
        response = client.chat.completions.create(**kwargs)
    except Exception as e:
        raise RuntimeError(f"OpenAI API call failed: {e}")

    if response and hasattr(response, "usage"):
        log_gpt_call(
            field_name=label,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            context_scope=context_scope or "full_text",
            model_name=model,
            record_id=record_id,
        )

    if json_mode:
        content = response.choices[0].message.content
        try:
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            return json.loads(content)
        except Exception as e:
            raise ValueError(f"Could not parse JSON for {label}: {e}")
    else:
        return response.choices[0].message.content.strip() if response else ""
