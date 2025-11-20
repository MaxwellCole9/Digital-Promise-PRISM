import os
import pathlib
import yaml
import json
from typing import Dict, Any, Tuple, Optional
from prism.extractors import get_llm_response

from rich.console import Console

console = Console()

DEFAULT_BATCH_PROMPT = """
Extract the following fields from the provided text.
Return a JSON object with these keys:
{field_names}

Do not add explanation or extra text.
Follow the specific instructions for each field.

{single_prompts}

Text:
{paper_text}
""".strip()


def load_field_config() -> Dict[str, Any]:
    config_path = os.getenv("FIELD_CONFIG", "config/field_definitions.yaml")
    try:
        with open(pathlib.Path(config_path), "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        raise RuntimeError(f"Failed to load field config: {e}")


class FieldProcessor:
    def __init__(self, config: Dict[str, Any]):
        self.fields = [f for f in config.get("fields", []) if isinstance(f, dict)]
        self.batches = self._build_batches()

    def _build_batches(self) -> Dict[str, Dict[str, Any]]:
        batch_map: Dict[str, Dict[str, Any]] = {}

        for field in self.fields:
            if not field.get("enabled", True):
                continue
            batch_name = field.get("batch")
            if not batch_name:
                continue
            if batch_name not in batch_map:
                batch_map[batch_name] = {
                    "name": batch_name,
                    "enabled": True,
                    "context_scope": self._default_context_scope(batch_name),
                    "structured_output": True,
                }

        return batch_map

    def _default_context_scope(self, batch_name: str) -> str:
        name = batch_name.lower()
        if "meta" in name:
            return "pre_intro"
        elif "abstract" in name:
            return "abstract"
        elif "outcome" in name:
            return "main_body"
        elif "semantic" in name:
            return "main_body"
        return "main_body"

    def process_fields(
        self,
        full_text: str,
        doc: Any,
        sections: Optional[Dict[str, str]] = None,
        record_id: Optional[str] = None,
        meta_fields: Optional[Dict[str, str]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:

        results = {}
        warnings = {}

        for batch_name, batch in self.batches.items():
            if not batch.get("enabled", True):
                continue

            batch_fields = [
                f for f in self.fields
                if f.get("enabled", True)
                and f.get("batch") == batch_name
                and f.get("prompt")
            ]
            if not batch_fields:
                continue

            # Determine scoped text FIRST
            scope = batch.get("context_scope")
            scoped_text = (
                sections.get(scope, full_text)
                if scope and sections
                else full_text
            )
            if scope and sections and not scoped_text.strip():
                scoped_text = full_text

            # Build prompt variables
            field_names = ", ".join(f["name"] for f in batch_fields)
            single_prompts = "\n".join(f["prompt"].strip() for f in batch_fields)

            prompt_vars = {
                "field_names": field_names,
                "single_prompts": single_prompts,
                "paper_text": scoped_text,   # ✔️ FIXED: Now defined AND included
            }

            try:
                prompt = DEFAULT_BATCH_PROMPT.format(**prompt_vars)
            except KeyError as e:
                warnings[batch_name] = f"Prompt formatting error: {e}"
                continue

            try:
                response = get_llm_response(
                    scoped_text,
                    prompt,
                    label=batch_name,
                    context_scope=scope,
                    record_id=record_id,
                    json_mode=batch.get("structured_output", True),
                    prompt_vars=prompt_vars,
                )

                if not isinstance(response, dict):
                    try:
                        response = json.loads(response)
                    except Exception as e:
                        warnings[batch_name] = f"Invalid JSON: {e}"
                        continue

                missing = []
                for f in batch_fields:
                    name = f["name"]
                    results[name] = response.get(name)
                    if name not in response:
                        missing.append(name)

                if missing:
                    warnings[batch_name] = f"Missing fields: {', '.join(missing)}"

            except Exception as e:
                warnings[batch_name] = str(e)

        return results, warnings
