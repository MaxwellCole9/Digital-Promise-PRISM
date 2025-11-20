import prism.airtable_client as airtable_client
import requests


class MockResponse:
    def __init__(self, json_data=None, status_code=200, text=""):
        self._json = json_data or {}
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)


def test_get_new_records(monkeypatch):
    def mock_get(url, headers=None, params=None, timeout=None):
        return MockResponse({"records": [{"id": "rec1"}]})

    monkeypatch.setattr(airtable_client.session, "get", mock_get)
    records = airtable_client.get_new_records()
    assert records == [{"id": "rec1"}]


def test_update_record_success(monkeypatch):
    def mock_patch(url, headers=None, json=None, timeout=None):
        return MockResponse(status_code=200)

    monkeypatch.setattr(airtable_client.session, "patch", mock_patch)

    log_calls = {}

    def fake_success(record_id, fields=None, success=True, values=None):
        log_calls["record_id"] = record_id
        log_calls["fields"] = list(fields)

    monkeypatch.setattr(airtable_client, "log_airtable_success", fake_success)
    result = airtable_client.update_record("rec1", {"Field": "Value"})

    assert result is True
    assert log_calls["record_id"] == "rec1"
    assert log_calls["fields"] == ["Field"]


def test_get_record_by_id(monkeypatch):
    def mock_get(url, headers=None, timeout=None):
        return MockResponse({"id": "rec1"})

    monkeypatch.setattr(airtable_client.session, "get", mock_get)
    record = airtable_client.get_record_by_id("rec1")
    assert record["id"] == "rec1"


def test_get_record_by_field(monkeypatch):
    def mock_get(url, headers=None, params=None, timeout=None):
        return MockResponse({"records": [{"id": "rec1"}]})

    monkeypatch.setattr(airtable_client.session, "get", mock_get)
    record = airtable_client.get_record_by_field("Name", "Alice")
    assert record["id"] == "rec1"


def test_set_processing_status_with_error(monkeypatch):
    captured = {}

    def mock_update(record_id, fields):
        captured["record_id"] = record_id
        captured["fields"] = fields
        return True

    monkeypatch.setattr(airtable_client, "update_record", mock_update)

    airtable_client.set_processing_status("rec1", "Failed", "oops")

    assert captured["record_id"] == "rec1"
    assert captured["fields"] == {"Processing Status": "Failed", "Error": "oops"}


def test_set_processing_status_without_error_clears_error(monkeypatch):
    captured = {}

    def mock_update(record_id, fields):
        captured["record_id"] = record_id
        captured["fields"] = fields
        return True

    monkeypatch.setattr(airtable_client, "update_record", mock_update)

    airtable_client.set_processing_status("rec1", "Complete")

    assert captured["record_id"] == "rec1"
    assert captured["fields"] == {
        "Processing Status": "Complete",
        "Error": None,
    }
