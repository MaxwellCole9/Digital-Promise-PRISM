import prism.webhook_client as webhook_client
from prism.main import ProcessingError


def test_process_record_sets_error_when_doi_missing(monkeypatch):
    calls = []

    def mock_get_record(record_id):
        count = mock_get_record.count
        mock_get_record.count += 1
        if count == 0:
            return {"fields": {}}
        else:
            return {"fields": {"DOI/URL": ""}}
    mock_get_record.count = 0
    monkeypatch.setattr(webhook_client, "get_record_by_id", mock_get_record)

    def mock_set_status(record_id, status, error_message=None):
        calls.append((record_id, status, error_message))
    monkeypatch.setattr(webhook_client, "set_processing_status", mock_set_status)

    def mock_process(record_id):
        pass
    monkeypatch.setattr(webhook_client, "process_record_by_id", mock_process)

    webhook_client.process_record_async_with_status("rec1")
    assert calls[0] == ("rec1", "Processing", None)
    assert calls[1] == ("rec1", "Complete", "DOI/URL not found")


def test_process_record_sets_complete_without_error(monkeypatch):
    calls = []

    def mock_get_record(record_id):
        count = mock_get_record.count
        mock_get_record.count += 1
        if count == 0:
            return {"fields": {}}
        else:
            return {"fields": {"DOI/URL": "http://example.com"}}
    mock_get_record.count = 0
    monkeypatch.setattr(webhook_client, "get_record_by_id", mock_get_record)

    def mock_set_status(record_id, status, error_message=None):
        calls.append((record_id, status, error_message))
    monkeypatch.setattr(webhook_client, "set_processing_status", mock_set_status)

    def mock_process(record_id):
        pass
    monkeypatch.setattr(webhook_client, "process_record_by_id", mock_process)

    webhook_client.process_record_async_with_status("rec1")
    assert calls[0] == ("rec1", "Processing", None)
    assert calls[1] == ("rec1", "Complete", None)


def test_process_record_sets_failed_on_processing_error(monkeypatch):
    calls = []

    def mock_get_record(record_id):
        return {"fields": {}}

    monkeypatch.setattr(webhook_client, "get_record_by_id", mock_get_record)

    def mock_set_status(record_id, status, error_message=None):
        calls.append((record_id, status, error_message))

    monkeypatch.setattr(webhook_client, "set_processing_status", mock_set_status)

    def mock_process(record_id):
        raise ProcessingError("boom")

    monkeypatch.setattr(webhook_client, "process_record_by_id", mock_process)

    webhook_client.process_record_async_with_status("rec1")
    assert calls[0] == ("rec1", "Processing", None)
    assert calls[1] == ("rec1", "Failed", "boom")
