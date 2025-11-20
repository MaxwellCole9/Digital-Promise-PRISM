import os
from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from prism.status import log_airtable_error, log_airtable_success

load_dotenv()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")
TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")
PROMPTS_TABLE = os.getenv("PROMPTS_TABLE", "Prompts")
HEADERS = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
BASE_URL = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"


retry_strategy = Retry(
    total=3,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "PATCH"],
    backoff_factor=1,
)
session = requests.Session()
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
session.mount("http://", adapter)

TIMEOUT = 10

# -----------------------------------------------------------
# get_new_records
# Fetches Airtable records that have PDFs and lack key summary fields.
# IN: None
# OUT: list of record dicts
# -----------------------------------------------------------
def get_new_records():
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
    params = {
        "filterByFormula": "AND({PDF}, NOT({Main Outcome Statement}), NOT({Findings/Outcomes}))"
    }
    try:
        res = session.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
        res.raise_for_status()
    except requests.RequestException as exc:
        log_airtable_error(
            "FETCH_NEW",
            status_code=getattr(getattr(exc, "response", None), "status_code", None),
            response_text=str(exc),
        )
        raise
    return res.json().get("records", [])


# -----------------------------------------------------------
# update_record
# Applies field updates to a specific Airtable record and logs the result.
# IN: record_id (str), fields (dict)
# OUT: True on success
# -----------------------------------------------------------
def update_record(record_id, fields):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}/{record_id}"
    data = {"fields": fields}

    try:
        res = session.patch(
            url,
            headers={**HEADERS, "Content-Type": "application/json"},
            json=data,
            timeout=TIMEOUT,
        )
        res.raise_for_status()
    except requests.RequestException as exc:
        log_airtable_error(
            record_id,
            status_code=getattr(getattr(exc, "response", None), "status_code", None),
            response_text=str(exc),
        )
        raise
    log_airtable_success(
        record_id, fields=fields.keys(), success=True, values=fields
    )
    return True


# -----------------------------------------------------------
# get_record_by_id
# Retrieves a specific Airtable record by its ID.
# IN: record_id (str)
# OUT: record dict
# -----------------------------------------------------------
def get_record_by_id(record_id):
    url = f"{BASE_URL}/{record_id}"
    try:
        res = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        res.raise_for_status()
    except requests.RequestException as exc:
        log_airtable_error(
            record_id,
            status_code=getattr(getattr(exc, "response", None), "status_code", None),
            response_text=str(exc),
        )
        raise

    return res.json()


# -----------------------------------------------------------
# clear_all_non_pdf_fields
# Clears non-PDF fields for every record with a PDF to force reprocessing.
# IN: None
# OUT: None
# -----------------------------------------------------------
def clear_all_non_pdf_fields():
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
    offset = None

    while True:
        params = {
            "filterByFormula": "NOT({PDF} = '')",
            "pageSize": 100,
        }
        if offset:
            params["offset"] = offset

        try:
            res = session.get(
                url, headers=HEADERS, params=params, timeout=TIMEOUT
            )
            res.raise_for_status()
        except requests.RequestException as exc:
            log_airtable_error(
                "CLEAR",
                status_code=getattr(getattr(exc, "response", None), "status_code", None),
                response_text=str(exc),
            )
            raise
        data = res.json()
        records = data.get("records", [])

        if not records:
            break

        for rec in records:
            record_id = rec["id"]
            fields = rec.get("fields", {})

            fields_to_clear = {key: None for key in fields if key != "PDF"}

            update_url = f"{url}/{record_id}"
            try:
                patch_resp = session.patch(
                    update_url,
                    headers=HEADERS,
                    json={"fields": fields_to_clear},
                    timeout=TIMEOUT,
                )
                patch_resp.raise_for_status()
                print(f"Cleared non-PDF fields for record {record_id}")
            except requests.RequestException as exc:
                print(f"Failed to clear record {record_id}: {exc}")
                raise

        offset = data.get("offset")
        if not offset:
            break


# -----------------------------------------------------------
# get_record_by_field
# Looks up a single Airtable record by a given field name and value.
# Returns the first match, or None if not found.
# IN: field_name (str), value (str)
# OUT: record (dict) or None
# -----------------------------------------------------------
def get_record_by_field(field_name, value):
    filter_formula = f"{{{field_name}}} = '{value}'"
    url = f"{BASE_URL}"
    params = {
        "filterByFormula": filter_formula,
        "maxRecords": 1,
    }

    try:
        res = session.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
        res.raise_for_status()
    except requests.RequestException as exc:
        log_airtable_error(
            "LOOKUP",
            status_code=getattr(getattr(exc, "response", None), "status_code", None),
            response_text=str(exc),
        )
        raise

    records = res.json().get("records", [])
    return records[0] if records else None

# -----------------------------------------------------------
# get_all_records
# Retrieves every record from the Airtable table with pagination handling.
# IN: None
# OUT: list of record dicts
# -----------------------------------------------------------
def get_all_records():
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
    records = []
    offset = None
    while True:
        params = {"pageSize": 100}
        if offset:
            params["offset"] = offset
        try:
            res = session.get(
                url, headers=HEADERS, params=params, timeout=TIMEOUT
            )
            res.raise_for_status()
        except requests.RequestException as exc:
            log_airtable_error(
                "FETCH_ALL",
                status_code=getattr(getattr(exc, "response", None), "status_code", None),
                response_text=str(exc),
            )
            raise
        data = res.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records


# -----------------------------------------------------------
# set_processing_status
# Updates the processing status and optional error field for a record.
# IN: record_id (str), status (str), error_message (str or None)
# OUT: None
# -----------------------------------------------------------
def set_processing_status(record_id, status, error_message=None):
    fields = {"Processing Status": status}
    if error_message:
        fields["Error"] = error_message
    else:
        fields["Error"] = None
    update_record(record_id, fields)
