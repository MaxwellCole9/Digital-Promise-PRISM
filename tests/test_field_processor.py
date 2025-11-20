import prism.field_processor as fp_module
from prism.field_processor import FieldProcessor


def test_process_fields(monkeypatch):
    config = {
        "auto_fields": {"Abstract": "sections.abstract"},
        "fields": [
            {"name": "Summary", "prompt": "Summarize", "batch": "main", "enabled": True}
        ],
        "batches": [{"name": "main", "prompt": "Batch prompt", "enabled": True}],
    }
    processor = FieldProcessor(config)

    def fake_get_llm_response(
        text,
        batch_prompt,
        label=None,
        context_scope=None,
        record_id=None,
        json_mode=False,
        prompt_vars=None,
    ):
        return {"Summary": "LLM result"}

    monkeypatch.setattr(fp_module, "get_llm_response", fake_get_llm_response)

    sections = {"abstract": "Abstract text"}
    results, warnings = processor.process_fields("Full text", None, sections=sections)

    assert results["Abstract"] == "Abstract text"
    assert results["Summary"] == "LLM result"
    assert warnings == {}
