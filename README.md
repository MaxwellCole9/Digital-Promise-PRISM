<p align="center">
  <img src="assets/prism-logo-blue.png" alt="PRISM Logo" width="400"/>
</p>

# PRISM – AI Research Paper Processor

**PRISM** automates the extraction and structuring of research insights from academic papers, integrating tightly with Airtable and OpenAI’s GPT models. Designed for **Digital Promise**, it streamlines literature review workflows by parsing PDFs, analyzing content with configurable prompts, and writing results directly to Airtable records.

This pipeline ensures consistent academic-style summaries, supports auditability, and tracks token-level usage for every model call.

---

## Key Capabilities

- **Seamless Airtable Integration**  
  Fetches new records with PDFs, applies GPT-driven extraction, and writes structured results back to Airtable. Supports record-level error handling, field resets, and Excel exports.

- **Context-Aware PDF Segmentation**  
  Parses academic PDFs into logical components (e.g., pre-intro, abstract, body, end matter). Detects metadata like publication year, DOI, arXiv ID, and institutional affiliations.

- **Configurable Prompt Batching**  
  Uses a YAML-based field configuration (`field_definitions.yaml`) to group related prompts into context-aware batches. Allows precise control over input scope and output formatting.

- **Model Usage Auditing**  
  Tracks every LLM call per record with input/output token counts, scope context, and model version.

- **Flexible Execution Modes**  
  Supports command-line usage, interactive terminal menu, and webhook-based asynchronous processing.

---

## Requirements

- Python 3.10 or higher  
- OpenAI API credentials (`GPT_KEY`)  
- Airtable API key, base ID, and table name  
- System dependencies for [PyMuPDF](https://pymupdf.readthedocs.io/) (`libmupdf`)

---

## Installation

```bash
git clone https://github.com/MaxwellCole9/PRISM.git
cd PRISM
pip install .
# Or, for local development:
pip install -e .[dev]
```

Create a `.env` file in the project root with the following variables:

```
GPT_KEY=sk-...
GPT_MODEL=gpt-4o
AIRTABLE_API_KEY=pat...
AIRTABLE_BASE_ID=app...
AIRTABLE_TABLE_NAME=Table%201
PROMPTS_TABLE=Prompts
FIELD_CONFIG=config/field_definitions.yaml
PRISM_API_SECRET=shared-secret-token
```

---

## Command-Line Usage

PRISM is functional without a webhosted environment, however generation must be triggered from the CLI manually. Hosting the webhook server allows automated requests to trigger the system.

```bash
# Process new Airtable records (default mode)
prism

# Process a single record by ID
prism --record-id recXXXXXXX

# Force reprocess all records
prism --force-all

# Save extracted text sections for audit
prism --save-text

# Launch the interactive menu
prism --interactive
```

---

## Webhook Deployment

PRISM includes a lightweight Flask service to support external automation:

```bash
export FLASK_APP=prism.webhook_client:app
flask run --host 0.0.0.0 --port 10000
```

Send POST requests to `/process` with a valid record ID and secret:

```json
{
  "record_id": "recXXXX",
  "token": "shared-secret-token"
}
```

Status endpoints are also available:

- `GET /status/<record_id>` – Returns current processing status  
- `GET /healthz` – Health check endpoint

---

## Configuration: Field Extraction via YAML

The core logic for extraction is defined in `config/field_definitions.yaml`.

Each field specifies:
- `name`: Airtable column name
- `enabled`: toggle field on/off
- `prompt`: the GPT instruction
- `batch`: group of fields sharing a context
- `context_scope`: (optional) section of the paper to analyze

Example:

```yaml
- name: Findings/Outcomes
  enabled: true
  type: long
  prompt: |
    Findings/Outcomes: Produce 3–4 bullet points (each starting with "- ") summarizing study context (first bullet) and key findings. Use neutral tone, no inference or redundancy; end each with a period.
  batch: outcomes_batch
```

---

## Prompt Design Guidelines

- Use clear, directive language: *Extract*, *List*, *Summarize*, etc.  
- Keep prompts declarative and avoid speculative phrasing  
- Ensure batch grouping aligns fields with shared context (e.g., `main_body`)  
- For structured output, ensure `structured_output: true` in batch definition  
- Disable unused fields by setting `enabled: false`

---

## Available Prompt Batches

These batch names are defined in `field_definitions.yaml` and are used to logically group prompts for efficient and scoped GPT interactions:

```
- metadata_batch
- semantic_batch
- outcomes_batch
- abstract_batch
```

Each batch is assigned a specific section of the paper:

- `metadata_batch`: operates on the pre-intro or front matter  
- `abstract_batch`: targets the abstract section  
- `semantic_batch`: analyzes main body context for classification and tagging  
- `outcomes_batch`: extracts structured findings and outcome summaries

---

## Development & Testing

```bash
black prism
flake8 prism
pytest
```

All configurations follow [PEP 517/518](https://peps.python.org/pep-0517/) via `pyproject.toml`.

---

## File Overview

| Path | Description |
|------|-------------|
| `main.py` | Core orchestration and CLI logic |
| `webhook_client.py` | Asynchronous processing via HTTP |
| `pdf_loader.py` | PDF download, parsing, sectioning |
| `field_processor.py` | LLM batch prompt construction and response handling |
| `extractors.py` | OpenAI API wrapper with rate limiting |
| `airtable_client.py` | Airtable record I/O |
| `status.py` | Console display and token logging |
| `config/field_definitions.yaml` | Prompt and field definitions |
| `config/msi_list.csv` | List of MSI institutions (optional) |

---

## Support

For setup assistance or contributions, please contact:

**max.cole4444@gmail.com**
