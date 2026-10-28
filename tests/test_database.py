"""Tests for database.py. They use a temporary database, never your real one."""

import database


def make_result(name="Monstera"):
    return {
        "common_name": name,
        "scientific_name": "Monstera deliciosa",
        "confidence": "high",
        "description": "A climbing plant with split leaves.",
        "care": {"sunlight": "Bright, indirect light."},
    }


def test_init_db_creates_database_file(tmp_path):
    db_file = tmp_path / "sub" / "test.db"
    database.init_db(db_file)
    assert db_file.exists()


def test_init_db_can_run_twice(tmp_path):
    db_file = tmp_path / "test.db"
    database.init_db(db_file)
    database.init_db(db_file)  # must not raise
    assert database.list_identifications(db_file) == []


def test_save_and_get_roundtrip(tmp_path):
    db_file = tmp_path / "test.db"
    database.init_db(db_file)
    new_id = database.save_identification(make_result(), db_file)

    saved = database.get_identification(new_id, db_file)
    assert saved["common_name"] == "Monstera"
    assert saved["scientific_name"] == "Monstera deliciosa"
    assert saved["details"]["care"]["sunlight"] == "Bright, indirect light."
    assert saved["created_at"]  # a timestamp was stored


def test_list_is_newest_first(tmp_path):
    db_file = tmp_path / "test.db"
    database.init_db(db_file)
    database.save_identification(make_result("First"), db_file)
    database.save_identification(make_result("Second"), db_file)
    names = [item["common_name"] for item in database.list_identifications(db_file)]
    assert names == ["Second", "First"]


def test_delete_removes_only_that_record(tmp_path):
    db_file = tmp_path / "test.db"
    database.init_db(db_file)
    first = database.save_identification(make_result("Keep"), db_file)
    second = database.save_identification(make_result("Remove"), db_file)

    assert database.delete_identification(second, db_file) is True
    remaining = database.list_identifications(db_file)
    assert [item["id"] for item in remaining] == [first]


def test_delete_missing_record_returns_false(tmp_path):
    db_file = tmp_path / "test.db"
    database.init_db(db_file)
    assert database.delete_identification(999, db_file) is False


def test_get_missing_record_returns_none(tmp_path):
    db_file = tmp_path / "test.db"
    database.init_db(db_file)
    assert database.get_identification(123, db_file) is None


def test_sql_injection_text_is_stored_as_plain_text(tmp_path):
    db_file = tmp_path / "test.db"
    database.init_db(db_file)
    evil = "x'); DROP TABLE identifications; --"
    new_id = database.save_identification(make_result(evil), db_file)
    assert database.get_identification(new_id, db_file)["common_name"] == evil
    assert len(database.list_identifications(db_file)) == 1
