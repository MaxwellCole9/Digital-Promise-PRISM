<p align="center" style="background-color: white; padding: 10px; border-radius: 8px; display: inline-block;">
  <img src="assets/prism-logo-blue.png" alt="PRISM Logo" width="400"/>
</p>

# PRISM – AI Research Paper Processor

**PRISM** automates the research-paper review workflow for **Digital Promise**, integrating with Airtable and OpenAI’s language models to extract, summarize, and structure research insights.  
It ingests PDFs or online papers, parses their sections, and runs configurable prompt batches that generate structured outputs directly into Airtable.

This system minimizes manual review, ensures consistent academic-style summaries, and provides traceable, token-level transparency for every model call.

---

## Key Capabilities

- **End-to-end Airtable integration**  
  Fetches records that contain attached PDFs, runs extractions, writes LLM results, and logs processing states or errors. Supports field resets and full exports to Excel.

- **PDF and metadata ingestion**  
  Extracts and segments PDFs into core sections (Abstract, Main Body, End Matter).  
  Detects metadata such as publication year, DOI/arXiv ID, and MSI institutions.

- **Config-driven LLM prompting**  
  Uses YAML-based configuration to define auto-copied fields and structured prompt batches, allowing flexible control of how and where the model reads from (e.g., pre-intro, abstract, main body).

- **Model usage transparency**  
  Tracks every OpenAI call with input/output token counts, recording model, scope, and record IDs.

- **Flexible execution modes**  
  Run as a batch CLI tool, through an interactive terminal menu, or as a Flask webhook for asynchronous processing from other systems.

---

## Requirements

- Python 3.10+
- OpenAI API key (`GPT_KEY`)
- Airtable API key, base ID, and table name
- [PyMuPDF](https://pymupdf.readthedocs.io/) dependencies (`libmupdf`, etc.)

---

## Installation

```bash
git clone https://github.com/MaxwellCole9/PRISM.git
cd PRISM
pip install .
# or, for development:
pip install -e .[dev]
```

Create a `.env` file in the project root:

```
GPT_KEY=sk-...
GPT_MODEL=gpt-4o-mini
AIRTABLE_API_KEY=pat...
AIRTABLE_BASE_ID=app...
AIRTABLE_TABLE_NAME=Table%201
PROMPTS_TABLE=Prompts
FIELD_CONFIG=config/field_definitions.yaml
PRISM_API_SECRET=shared-secret-for-webhook
```

---

## Usage

PRISM installs a console command named `prism`.

```bash
# Process all new Airtable records with PDFs
prism

# Process a single record by ID
prism --record-id recXXXXXXX

# Force reprocess all records (clears non-PDF fields)
prism --force-all

# Save extracted sections as plaintext
prism --save-text

# Launch the interactive CLI menu
prism --interactive
```

The interface displays live progress, success/failure reports, and a per-run GPT token summary.

---

## Webhook Deployment

You can run PRISM as a service endpoint for asynchronous automation:

```bash
export FLASK_APP=prism.webhook_client:app
flask run --host 0.0.0.0 --port 10000
```

Send a POST request to `/process` with the Airtable record ID and secret:

```json
{"record_id": "recXXXX", "token": "shared-secret-for-webhook"}
```

The record’s **Processing Status** and **Error** fields are automatically updated in Airtable.  
A live status dashboard is available at `/status`.

---

## Configuration: Custom Prompts and Field Extraction

PRISM’s entire extraction logic is defined in `config/field_definitions.yaml`.  
This YAML file determines which fields are copied directly from the document and which require LLM extraction.

### Configuration Structure

```yaml
auto_fields:
  - Abstract

batches:
  - name: metadata_batch
    context_scope: pre_intro
    structured_output: true
    prompt: |
      Extract the following fields from the provided text.
      Return a JSON object with these keys:
      {field_names}
      {single_prompts}

  - name: outcomes_batch
    context_scope: main_body
    structured_output: true
    prompt: |
      Extract the following fields from the provided text.
      Return a JSON object with these keys:
      {field_names}
      {single_prompts}

  - name: semantic_batch
    context_scope: main_body
    structured_output: true
    prompt: |
      Extract the following fields from the provided text.
      Return a JSON object with these keys:
      {field_names}
      {single_prompts}
```

Each **batch** defines a shared context (which paper section is used), a structured format, and a general instruction that combines all individual field prompts within it.

---

### Fields Overview

Each `field` entry in the YAML defines:
- `name`: must match the Airtable column name  
- `enabled`: controls whether the field is processed  
- `type`: `"short"` or `"long"` to describe expected output length  
- `prompt`: the model instruction for that field  
- `batch`: links to one of the defined batches  
- `context_scope`: optional, used only for standalone fields

Examples from the current configuration:

| Batch | Field Name | Description |
|-------|-------------|-------------|
| `metadata_batch` | **Study Short Name** | Creates a citation-style shorthand like “Nguyen et al., 2023”. |
| `metadata_batch` | **Title**, **Author(s)**, **Pub Year**, **DOI/URL** | Extract bibliographic metadata and identifiers. |
| `metadata_batch` | **MSI Associated** | Reads “Possible MSI Institutions:” from pre-intro text. |
| `semantic_batch` | **Paper Type**, **Evidence Tier**, **AI Model(s)** | Categorizes study design and identifies mentioned AI models. |
| `semantic_batch` | **Funding Source/Sponsorship**, **Bias/Equity Concerns** | Returns concise factual entries. |
| `outcomes_batch` | **Main Outcome Statement**, **Findings/Outcomes** | Summarizes primary results and supporting bullet points. |

---

### Writing and Testing Your Own Prompts

1. **Add new fields** under `fields:` and assign them to an existing or new batch.  
2. Keep prompts short and declarative. Example:
   ```yaml
   - name: Intervention Summary
     enabled: true
     type: long
     prompt: |
       In one or two sentences, summarize the main intervention or system described in the study.
       Use only factual statements from the text.
     batch: outcomes_batch
   ```
3. If your field should only analyze a specific section, assign:
   ```yaml
   context_scope: abstract
   ```
4. To test a prompt’s behavior:
   ```bash
   prism --record-id recXXXX --save-text
   ```
   Review the resulting `.txt` file and Airtable output to tune prompt precision.

---

### Prompt Design Guidelines

- Always include **clear instruction verbs** (“Return”, “List”, “Classify”, “Extract”).  
- Use **neutral tone** and avoid inference language.  
- When returning structured values (JSON), ensure the batch uses `structured_output: true`.  
- Place logically related fields in the same batch to reduce model calls and cost.  
- To disable a field temporarily, set `enabled: false`.

---

## Development and Testing

Code quality and testing are standardized with:

```bash
black prism
flake8 prism
pytest
```

All configuration and test coverage are compatible with CI/CD setups through `pyproject.toml`.

---

## Project Layout

| File | Purpose |
|------|----------|
| `main.py` | Command-line entry point and orchestration |
| `pdf_loader.py` | PDF parsing, section detection, MSI matching |
| `field_processor.py` | Loads YAML config and executes LLM field batches |
| `extractors.py` | Handles OpenAI calls and token logging |
| `airtable_client.py` | Airtable REST communication and record updates |
| `status.py` | Rich-based logging and run summaries |
| `webhook_client.py` | Flask app for asynchronous HTTP-based processing |
| `config/field_definitions.yaml` | Field, batch, and prompt configuration |
| `config/msi_list.csv` | MSI institution reference list |

---

## Support

For setup help or collaboration inquiries, contact  
**max.cole4444@gmail.com**
