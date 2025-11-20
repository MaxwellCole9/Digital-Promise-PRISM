import argparse
import sys
import pandas as pd
from datetime import datetime
import os

from prism.airtable_client import (
    get_new_records,
    update_record,
    get_record_by_id,
    get_record_by_field,
    clear_all_non_pdf_fields,
    get_all_records,
)
from prism.pdf_loader import extract_text_from_attachment
from prism.field_processor import FieldProcessor, load_field_config
from prism.status import (
    log_processing,
    log_success,
    log_error,
    print_summary,
    print_gpt_usage_summary,
)

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from readchar import readkey

console = Console()


class ProcessingError(Exception):
    """Raised when a record cannot be processed successfully."""


# -----------------------------------------------------------
# export_airtable_to_excel
# Exports all Airtable records to an Excel file in the exports folder.
# IN: None
# OUT: None
# -----------------------------------------------------------
def export_airtable_to_excel():
    records = get_all_records()
    if not records:
        print("[INFO] No records found in Airtable to export.")
        return

    export_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "exports"
    )
    os.makedirs(export_dir, exist_ok=True)

    rows = []
    for rec in records:
        row = dict(rec.get("fields", {}))
        row["AirtableID"] = rec.get("id")
        rows.append(row)

    df = pd.DataFrame(rows)
    filename = f"airtable_export_{datetime.now():%Y-%m-%d_%H%M%S}.xlsx"
    full_path = os.path.join(export_dir, filename)
    df.to_excel(full_path, index=False)
    console.print(f"[green]Exported all Airtable records to: {full_path}[/green]")


# -----------------------------------------------------------
# process_record_by_id
# Processes a specific Airtable record by ID using configured field logic.
# IN: record_id (str), save_text (bool)
# OUT: None
# -----------------------------------------------------------
def process_record_by_id(record_id, save_text=False):
    from prism.field_processor import FieldProcessor, load_field_config

    config = load_field_config()
    processor = FieldProcessor(config)

    record = get_record_by_id(record_id)
    if record:
        process_single_record(record, processor, save_text=save_text)
    else:
        print(f"[ERROR] Record {record_id} not found.")


# -----------------------------------------------------------
# postprocess_results
# Normalizes processed field results by joining list values with newlines.
# IN: results (dict)
# OUT: dict with string values
# -----------------------------------------------------------
def postprocess_results(results):
    return {k: "\n".join(v) if isinstance(v, list) else v for k, v in results.items()}


# -----------------------------------------------------------
# save_plaintext_sections
# Writes extracted section text to a plaintext file for auditing purposes.
# IN: record_id (str), sections (dict)
# OUT: None
# -----------------------------------------------------------
def save_plaintext_sections(record_id, sections):
    base = f"{record_id}_plaintext"
    with open(f"{base}.txt", "w", encoding="utf-8") as f:
        for key, section_text in sections.items():
            f.write(f"\n\n===== {key.upper()} =====\n\n")
            f.write(section_text)
    print(f"  ↳ Sectioned plaintext saved to: {base}.txt")


# -----------------------------------------------------------
# process_single_record
# Handles end-to-end processing for a single Airtable record, including
# PDF extraction, field processing, and Airtable updates.
# IN: record (dict), processor (FieldProcessor), save_text (bool)
# OUT: None
# -----------------------------------------------------------
def process_single_record(record, processor, save_text=False):
    record_id = record["id"]
    fields = record.get("fields", {}) or {}

    had_user_url = bool(fields.get("DOI/URL"))
    canonical_source_url = None

    attachment = None
    pdf_list = fields.get("PDF") or []
    if isinstance(pdf_list, list) and len(pdf_list) > 0:
        attachment = pdf_list[0]

    if attachment is None:
        source_url = fields.get("DOI/URL") or fields.get("Source URL")
        if source_url:
            url = str(source_url).strip()
            if "arxiv.org/abs/" in url:
                arxiv_id = url.rstrip("/").split("/")[-1]
                canonical_source_url = f"https://arxiv.org/abs/{arxiv_id}"
                url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            else:
                canonical_source_url = url
            attachment = {"url": url}

    if attachment is None:
        raise ProcessingError("Missing or invalid PDF attachment: 'PDF' and no DOI/URL")

    try:
        log_processing(record_id)

        pdf_data = extract_text_from_attachment(attachment)
        if not pdf_data or "sections" not in pdf_data:
            raise ProcessingError("PDF extraction returned no section data.")

        sections = pdf_data.get("sections", {})
        text = pdf_data.get("full_text") or "\n\n".join(sections.values())
        doc = pdf_data.get("doc")

        if save_text:
            save_plaintext_sections(record_id, sections)

        fields_to_update, warnings = processor.process_fields(
            text, doc, sections=sections, record_id=record_id
        )
        fields_to_update = postprocess_results(fields_to_update)

        if had_user_url and "DOI/URL" in fields_to_update:
            del fields_to_update["DOI/URL"]

        if not had_user_url and canonical_source_url:
            fields_to_update.setdefault("DOI/URL", canonical_source_url)

        if fields_to_update:
            update_succeeded = update_record(record_id, fields_to_update)
            if update_succeeded:

                try:
                    if not fields.get("PDF") and isinstance(attachment, dict) and "url" in attachment:
                        update_record(record_id, {"PDF": [attachment]})
                except Exception as e:
                    log_error(record_id, f"Failed to backfill PDF attachment: {e}")

                log_success(record_id, fields=fields_to_update.keys(), warnings=warnings)
            else:
                log_error(record_id, "Failed to update Airtable with extracted fields.")
        else:
            log_error(record_id, "No fields extracted successfully")

    except ProcessingError:
        raise
    except Exception as e:
        log_error(record_id, f"PDF processing failed: {e}")
        raise ProcessingError(f"PDF processing failed: {e}")


# -----------------------------------------------------------
# fetch_records
# Retrieves either all new records or a specific record by ID for processing.
# IN: record_id (str or None)
# OUT: list of record dicts
# -----------------------------------------------------------
def fetch_records(record_id=None):
    if record_id:
        print(f"[INFO] Processing specific record: {record_id}")
        record = get_record_by_id(record_id)
        if not record:
            print(f"[ERROR] Record {record_id} not found or failed to fetch.")
            return []
        return [record]
    else:
        return get_new_records()


# -----------------------------------------------------------
# prompt_for_record
# Requests a record identifier from the user and returns the Airtable record.
# IN: None
# OUT: record dict or None
# -----------------------------------------------------------
def prompt_for_record():
    user_input = input("Enter Study Short Name or Record ID: ").strip()
    if user_input.startswith("rec"):
        record = get_record_by_id(user_input)
        if not record:
            print(f"[ERROR] No record found with ID {user_input}")
        return record
    else:
        record = get_record_by_field("Study Short Name", user_input)
        if not record:
            print(f"[ERROR] No record found with Study Short Name '{user_input}'")
        return record


# -----------------------------------------------------------
# process_records
# Iterates through provided Airtable records and processes each one.
# IN: records (list), processor (FieldProcessor), save_text (bool)
# OUT: None
# -----------------------------------------------------------
def process_records(records, processor, save_text=False):
    if not records:
        print("[INFO] No records to process.")
        return
    for rec in records:
        process_single_record(rec, processor, save_text=save_text)


# -----------------------------------------------------------
# interactive_menu
# Provides a console interface for selecting common processing actions.
# IN: None
# OUT: None
# -----------------------------------------------------------
def interactive_menu():
    config = load_field_config()
    processor = FieldProcessor(config)

    MENU_OPTIONS = {
        "1": "Process all new records",
        "2": "Process a single record",
        "3": "Force-reprocess all records",
        "4": "Export all Airtable data to Excel",
        "q": "Exit",
    }

    while True:
        console.clear()
        console.print(f"[bold]PRISM[/bold] [dim]", justify="left")
        console.print(
            f"[dim]A Digital Promise Technology | Ver 1.0 |[/dim] [bold]Status Mode: [bold green]Detailed[/bold green][/bold]",
            justify="left",
        )

        table = Table(show_lines=True, style="bold")
        table.add_column("Option", style="cyan", justify="right")
        table.add_column("Action", style="white", justify="left")
        for k, v in MENU_OPTIONS.items():
            table.add_row(k, v)
        console.print(table)

        console.print(
            "[bold green]Select an option by pressing a single key (1-4 or q):[/] ",
            end="",
        )
        choice = readkey().lower()
        console.print(choice)

        match choice:
            case "1":
                records = get_new_records()
                process_records(records, processor)
                console.input("\n[bold yellow]Press Enter to return to menu...[/]")
            case "2":
                record = prompt_for_record()
                if record:
                    process_records([record], processor)
                console.input("\n[bold yellow]Press Enter to return to menu...[/]")
            case "3":
                console.print(
                    "[bold red]Warning:[/] This will clear ALL summary fields for ALL records in Airtable, "
                    "and re-extract from scratch. [bold]This cannot be undone.[/bold]"
                )
                console.print(
                    "[bold yellow]Are you sure you want to continue? (y/n):[/] ", end=""
                )
                confirm = readkey().lower()
                console.print(confirm)
                if confirm == "y":
                    console.print(
                        "[bold yellow]Proceeding with full reprocessing...[/]"
                    )
                    clear_all_non_pdf_fields()
                    records = get_new_records()
                    process_records(records, processor)
                    console.input("\n[bold yellow]Press Enter to return to menu...[/]")
                else:
                    console.print("[green]Cancelled. No changes were made.[/]")
                    console.input("\n[bold yellow]Press Enter to return to menu...[/]")
            case "4":
                console.print(
                    "[bold yellow]Exporting all Airtable records to Excel...[/]"
                )
                export_airtable_to_excel()
                console.input("\n[bold yellow]Press Enter to return to menu...[/]")
            case "q":
                console.print("[bold green]Exiting.[/]")
                sys.exit(0)
            case _:
                console.print(f"[bold red]Invalid choice: '{choice}'. Try again.[/]")
                console.input("[bold yellow]Press Enter to return to menu...[/]")


# -----------------------------------------------------------
# main
# Entry point for command-line execution of the PRISM processing pipeline.
# IN: save_text (bool), record_id (str or None), force_all (bool), interactive (bool)
# OUT: None
# -----------------------------------------------------------
def main(save_text=False, record_id=None, force_all=False, interactive=False):
    config = load_field_config()
    processor = FieldProcessor(config)

    if interactive:
        interactive_menu()
        return

    if force_all:
        print("[INFO] Forcing full reprocessing: clearing non-PDF fields...")
        clear_all_non_pdf_fields()
        records = get_new_records()
    else:
        records = fetch_records(record_id)

    process_records(records, processor, save_text=save_text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the PDF extraction pipeline.")
    parser.add_argument(
        "--save-text",
        action="store_true",
        help="Save extracted plaintext to .txt files",
    )
    parser.add_argument(
        "--record-id", type=str, help="Process a single record by Airtable ID"
    )
    parser.add_argument(
        "--force-all",
        action="store_true",
        help="Clear all non-PDF fields and reprocess all records",
    )
    parser.add_argument(
        "--interactive", action="store_true", help="Launch interactive menu"
    )
    args = parser.parse_args()

    main(
        save_text=args.save_text,
        record_id=args.record_id,
        force_all=args.force_all,
        interactive=args.interactive,
    )
