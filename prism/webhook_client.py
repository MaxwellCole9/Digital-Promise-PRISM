from flask import Flask, request, jsonify
from concurrent.futures import ThreadPoolExecutor
import os

from prism.airtable_client import set_processing_status, get_record_by_id
from prism.main import process_record_by_id, ProcessingError

app = Flask(__name__)

# Read secret from environment (as set in Render)
API_SECRET = os.getenv("PRISM_API_SECRET")

# Thread pool to avoid RAM exhaustion on Render
executor = ThreadPoolExecutor(max_workers=10)


def process_record_async_with_status(record_id):
    record = get_record_by_id(record_id)
    current_status = (record or {}).get("fields", {}).get("Processing Status")
    if current_status == "Processing":
        print(f"[INFO] Record {record_id} is already processing. Skipping.")
        return
    try:
        print(f"[INFO] Started processing record {record_id}")
        set_processing_status(record_id, "Processing")
        process_record_by_id(record_id)
    except ProcessingError as e:
        print(f"[ERROR] Processing record {record_id} failed: {e}")
        set_processing_status(record_id, "Failed", str(e))
        return
    except Exception as e:
        print(f"[ERROR] Processing record {record_id} failed: {e}")
        set_processing_status(record_id, "Failed", str(e))
        return
    updated_record = get_record_by_id(record_id)
    doi_url = (updated_record or {}).get("fields", {}).get("DOI/URL")
    if not doi_url or str(doi_url).strip() == "" or str(doi_url).strip().upper() == "N/A":
        set_processing_status(record_id, "Complete", "DOI/URL not found")
    else:
        set_processing_status(record_id, "Complete")
    print(f"[INFO] Completed processing record {record_id}")


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json(silent=True)
    if not data or not data.get("record_id"):
        return jsonify({"error": "Missing record_id"}), 400
    if data.get("token") != API_SECRET:
        return jsonify({"error": "Invalid API token"}), 403

    record_id = data["record_id"]
    # pdf_url can be extracted if needed, currently unused
    executor.submit(process_record_async_with_status, record_id)
    return jsonify({"status": "queued"}), 200


@app.route("/status/<record_id>", methods=["GET"])
def status(record_id):
    record = get_record_by_id(record_id)
    status = (record or {}).get("fields", {}).get("Processing Status")
    return jsonify({"record_id": record_id, "status": status or "Unknown"})


@app.route("/healthz", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
