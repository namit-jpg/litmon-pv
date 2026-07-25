from app.services.import_service import parse_articles_csv, parse_pmid_list


def test_parse_pmid_list():
    text = "123, 456;789\n101112"
    assert parse_pmid_list(text) == ["123", "456", "789", "101112"]


def test_parse_csv():
    csv = "pmid,title,abstract\n1,Hello,World\n2,Other,\n"
    rows = parse_articles_csv(csv)
    assert len(rows) == 2
    assert rows[0]["pmid"] == "1"
    assert rows[0]["title"] == "Hello"
