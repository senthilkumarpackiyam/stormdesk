"""Every reset keeps a copy of the old data first, and a backup can be put back."""

from stormdesk.config import settings
from stormdesk.store import backups
from tests.helpers import identify, verify


def calls(client):
    return [s["conversation_id"] for s in client.get("/admin/sessions").json()["sessions"]]


def test_reset_backs_up_first_and_restore_brings_it_back(client):
    verify(client, "c1")
    saved = client.post("/admin/reset", json={"confirm": True}).json()["backup"]
    assert saved and calls(client) == []
    assert (settings.db_path.parent / "backups" / f"{settings.db_path.stem}-{saved}.db").exists()

    restored, safety = backups.restore("latest")
    assert restored == saved and safety  # the data it replaced was kept too
    assert calls(client) == ["c1"]
    assert client.get("/admin/sessions/c1").json()["verified_at"]


def test_saves_in_the_same_second_do_not_overwrite_each_other(client):
    identify(client, "c1")
    first, second = backups.save(), backups.save()
    assert first != second and backups.names()[:2] == [second, first]


def test_only_the_newest_backups_are_kept(client, monkeypatch):
    monkeypatch.setattr(backups, "KEPT", 3)
    identify(client, "c1")
    made = [backups.save() for _ in range(5)]
    assert backups.names() == list(reversed(made[-3:]))
    assert len(list(backups.folder().glob(f"{settings.db_path.stem}-*.db"))) == 3  # older files are deleted


def test_nothing_to_back_up_on_an_empty_database(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "empty.db")
    assert backups.save() is None


def test_restore_refuses_an_unknown_name(client):
    identify(client, "c1")
    backups.save()
    try:
        backups.restore("19990101-000000")
    except ValueError as exc:
        assert "Available:" in str(exc)
    else:
        raise AssertionError("restored a backup that doesn't exist")
