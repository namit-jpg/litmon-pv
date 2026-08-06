from app.services.export_service import records_to_csv


def test_records_to_csv():
    rows = [
        {
            "pmid": "1",
            "title": "A",
            "suspect_products": ["atorvastatin"],
            "ai_reason_tags": [{"code": "x"}],
        }
    ]
    csv = records_to_csv(rows)
    assert "pmid" in csv
    assert "atorvastatin" in csv
    assert "1" in csv
