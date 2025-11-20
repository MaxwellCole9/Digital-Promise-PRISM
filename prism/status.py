from rich.console import Console
from rich.table import Table

console = Console()
record_usage = {}
_gpt_token_usage = {}
success_count = 0
failure_count = 0

# -----------------------------------------------------------
# log_processing
# Displays a processing banner for the given record and optional word count.
# IN: record_id (str), word_count (int or None)
# OUT: None
# -----------------------------------------------------------
def log_processing(record_id, word_count=None):
    console.rule(f"[bold blue]→ Processing Record: {record_id}")
    if word_count is not None:
        console.print(f"[bold]Word Count:[/] {word_count}")


# -----------------------------------------------------------
# log_success
# Records a successful processing message and displays any warnings.
# IN: record_id (str), fields (iterable), warnings (iterable), start_time (datetime or None)
# OUT: None
# -----------------------------------------------------------
def log_success(record_id, fields, warnings, start_time=None):
    global success_count
    success_count += 1
    console.print(f"[green]✔ Success:[/] Record {record_id} processed successfully.")
    if warnings:
        console.print("[yellow]Warnings:[/]")
        for w in warnings:
            console.print(f"  [yellow]● {w}")


# -----------------------------------------------------------
# log_error
# Records a failure message for the given record and error description.
# IN: record_id (str), message (str), start_time (datetime or None)
# OUT: None
# -----------------------------------------------------------
def log_error(record_id, message, start_time=None):
    global failure_count
    failure_count += 1
    console.print(f"[red]✖ Failure:[/] Record {record_id} failed.")
    console.print(f"[red]Reason: {message}[/]")


# -----------------------------------------------------------
# stop_processing
# Emits a completion banner after processing concludes.
# IN: None
# OUT: None
# -----------------------------------------------------------
def stop_processing():
    console.rule("[bold green]✔ Processing Complete")


# -----------------------------------------------------------
# print_summary
# Displays a summary table of successes, failures, and total GPT token usage.
# IN: None
# OUT: None
# -----------------------------------------------------------
def print_summary():
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Result", justify="right")
    table.add_column("Count", justify="center")
    table.add_row("Success", str(success_count))
    table.add_row("Failed", str(failure_count))
    gpt_total = sum(u["total"] for u in _gpt_token_usage.values())
    table.add_row("GPT Tokens", str(gpt_total))
    console.print(table)

    if len(_gpt_token_usage) > 1:
        per_rec = Table(show_header=True, header_style="dim")
        per_rec.add_column("Record ID")
        per_rec.add_column("Input")
        per_rec.add_column("Output")
        per_rec.add_column("Total")
        for rid, usage in _gpt_token_usage.items():
            per_rec.add_row(
                rid, str(usage["input"]), str(usage["output"]), str(usage["total"])
            )
        console.print(per_rec)


# -----------------------------------------------------------
# log_gpt_call
# Logs token usage for an LLM call and optionally prints a preview of output text.
# IN: field_name (str or None), input_tokens (int), output_tokens (int), context_scope (str or None),
#     model_name (str), output_text (str or None), record_id (str or None)
# OUT: None
# -----------------------------------------------------------
def log_gpt_call(
    field_name,
    input_tokens,
    output_tokens,
    context_scope,
    model_name,
    output_text=None,
    record_id=None,
):
    total = input_tokens + output_tokens
    width = console.size.width

    field_col = str(field_name)[:15].ljust(15)
    ctx_col = (context_scope or "full_text")[:10].ljust(10)
    tokens_col = f"[{input_tokens}|{output_tokens}|{total}]"
    summary = f"{field_col} | {ctx_col} | {tokens_col:15} | {model_name}"

    console.print(summary)
    if output_text and width > 80:
        preview = (
            (output_text[: width - 8] + "...")
            if len(output_text) > width - 8
            else output_text
        )
        console.print(f"[dim]{preview}[/dim]")

    if record_id:
        usage = _gpt_token_usage.setdefault(
            record_id, {"input": 0, "output": 0, "total": 0}
        )
        usage["input"] += input_tokens
        usage["output"] += output_tokens
        usage["total"] += total


# -----------------------------------------------------------
# print_gpt_usage_summary
# Prints cumulative GPT token usage for a specific record.
# IN: record_id (str)
# OUT: None
# -----------------------------------------------------------
def print_gpt_usage_summary(record_id):
    usage = _gpt_token_usage.get(record_id)
    if usage:
        console.print(f"[magenta]Total Tokens Used:[/] {usage['total']}\n")


# -----------------------------------------------------------
# log_airtable_error
# Reports an Airtable API error with optional status and response text.
# IN: record_id (str), status_code (int or None), response_text (str or None)
# OUT: None
# -----------------------------------------------------------
def log_airtable_error(record_id, status_code=None, response_text=None):
    console.print(
        f"[red][Airtable ERROR][/red] Record {record_id} - Status {status_code}"
    )
    if response_text:
        console.print(f"[dim]{response_text}[/dim]")


# -----------------------------------------------------------
# log_airtable_success
# Reports the outcome of an Airtable update and lists succeeded or empty fields.
# IN: record_id (str), fields (iterable or None), success (bool), values (dict or None)
# OUT: None
# -----------------------------------------------------------
def log_airtable_success(record_id, fields=None, success=True, values=None):
    if not success:
        console.print(f"[Airtable ERROR] Failed to update record {record_id}")
        return

    if not isinstance(fields, list):
        fields = list(fields or {})

    fallback_values = {"unknown", "n/a", "no funding received"}
    non_extraction_fields = []
    empty_fields = []
    succeeded = 0

    for k in fields:
        val = (values or {}).get(k)
        if not val:
            empty_fields.append(k)
        elif isinstance(val, str) and val.strip().lower() in fallback_values:
            non_extraction_fields.append(k)
        else:
            succeeded += 1

    console.print(
        f"[Airtable SUCCESS] Record {record_id} updated | Fields: {succeeded} succeeded, {len(non_extraction_fields)} non-extraction, {len(empty_fields)} failed"
    )
    if empty_fields:
        console.print(f"  ↳ Failed Fields: {empty_fields}")
    if non_extraction_fields:
        console.print(f"  ↳ Non-extraction Fields: {non_extraction_fields}")
