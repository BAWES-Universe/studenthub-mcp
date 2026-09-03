"""Integration tests: run the actual MCP tool functions against a real
MySQL fixture (loaded from tests/fixtures/schema.sql).

These run in CI against the mysql service container, or locally against
any MySQL reachable via SH_DB_* env vars (e.g. the dev clone).

IMPORTANT: tests call the tool functions directly (not over HTTP) but the
functions are the exact code the MCP server exposes.
"""

import json
import os

import pytest

# The server reads SH_DB_* from the environment at import time — these must
# be set BEFORE import. CI workflow sets them; locally set them to the
# dev clone before running.
pytestmark = pytest.mark.integration


def _env(name, default):
    return os.environ.get(name, default)


# Import AFTER env is available; server.py reads env at module import.
import server


def _data(payload: str) -> dict:
    return json.loads(payload)["data"]


@pytest.fixture(scope="module")
def db_ready():
    # Force a connection check — fail fast with a clear message if the
    # fixture DB isn't reachable.
    try:
        conn = server._connect()
        conn.close()
    except Exception as e:  # noqa: BLE001 - env setup failure path
        pytest.skip(f"MySQL fixture not reachable: {e}")
    return True


class TestSearchCandidates:
    def test_returns_all_with_no_filters(self, db_ready):
        payload = server.search_candidates(limit=50)
        data = _data(payload)
        assert len(data) == 4

    def test_country_filter(self, db_ready):
        payload = server.search_candidates(country="Egypt", limit=50)
        data = _data(payload)
        assert len(data) == 2
        assert all(r["candidate_country"] == "Egypt" for r in data)

    def test_name_query(self, db_ready):
        payload = server.search_candidates(query="Ali", limit=50)
        data = _data(payload)
        assert len(data) == 1
        assert data[0]["candidate_name"] == "Ali Hassan"

    def test_skill_filter(self, db_ready):
        payload = server.search_candidates(skill="Retail", limit=50)
        data = _data(payload)
        # Ali (skill deleted=0) matches; Sara's skill is deleted=1 → excluded
        names = {r["candidate_name"] for r in data}
        assert names == {"Ali Hassan"}

    def test_status_filter(self, db_ready):
        payload = server.search_candidates(status=0, limit=50)
        data = _data(payload)
        assert len(data) == 2  # Mona + Sara


class TestGetCandidateProfile:
    def test_full_profile_sections(self, db_ready):
        payload = server.get_candidate_profile(1)
        data = _data(payload)
        assert data["candidate"]["candidate_name"] == "Ali Hassan"
        assert len(data["skills"]) == 2
        assert len(data["education"]) == 1
        assert len(data["work_history"]) == 1
        assert len(data["links"]) == 1

    def test_missing_candidate_returns_not_found(self, db_ready):
        payload = server.get_candidate_profile(9999)
        assert json.loads(payload)["ok"] is False
        assert json.loads(payload)["error"] == "not_found"


class TestSearchRequests:
    def test_all_requests(self, db_ready):
        payload = server.search_requests(limit=50)
        data = _data(payload)
        assert len(data) == 2

    def test_status_filter(self, db_ready):
        payload = server.search_requests(status="delivered", limit=50)
        data = _data(payload)
        assert len(data) == 1
        assert data[0]["request_uuid"] == "request_def"

    def test_company_filter(self, db_ready):
        payload = server.search_requests(company_id=2, limit=50)
        data = _data(payload)
        assert len(data) == 1
        assert data[0]["company_name"] == "Zama"


class TestGetRequest:
    def test_request_with_applications(self, db_ready):
        payload = server.get_request("request_abc")
        data = _data(payload)
        assert data["request"]["request_position_title"] == "Sales Representative"
        assert data["company"][0]["company_name"] == "Azadea"
        assert len(data["applications"]) == 2

    def test_missing_request(self, db_ready):
        payload = server.get_request("request_nope")
        assert json.loads(payload)["error"] == "not_found"


class TestCompanies:
    def test_list_with_parent_names(self, db_ready):
        payload = server.get_companies(limit=50)
        data = _data(payload)
        by_id = {r["company_id"]: r for r in data}
        assert by_id[2]["parent_company_name"] == "Azadea"

    def test_company_tree(self, db_ready):
        payload = server.get_company_tree(1)
        data = _data(payload)
        assert data["company"]["company_name"] == "Azadea"
        assert data["parent"] is None
        assert {s["company_name"] for s in data["sub_companies"]} == {"Zama", "ALDA"}

    def test_sub_company_has_parent(self, db_ready):
        payload = server.get_company_tree(2)
        data = _data(payload)
        assert data["parent"]["company_name"] == "Azadea"


class TestReference:
    def test_countries_counts(self, db_ready):
        payload = server.get_countries(limit=50)
        data = _data(payload)
        by_country = {r["country"]: r["candidate_count"] for r in data}
        assert by_country["Kuwait"] == 1
        assert by_country["Egypt"] == 2

    def test_universities_with_candidate_counts(self, db_ready):
        payload = server.get_universities(limit=50)
        data = _data(payload)
        by_name = {r["university_name_en"]: r for r in data}
        assert by_name["Cairo University"]["candidate_count"] == 2
        assert by_name["Kuwait University"]["candidate_count"] == 1


class TestResolvePerson:
    def test_by_discord_id(self, db_ready):
        payload = server.resolve_person("123456789012345678")
        data = _data(payload)
        assert data["matched_by"] == "discord_id"
        assert data["matches"][0]["person"]["display_name"] == "Ali Hassan"
        # Ali has TWO universe player accounts and one candidate legacy link.
        assert set(data["matches"][0]["players"]) == {"player-abc", "player-xyz"}
        assert data["matches"][0]["identities"] == [
            {"account_type": "candidate", "legacy_id": "1"}
        ]

    def test_by_player_id(self, db_ready):
        payload = server.resolve_person("player-xyz")
        data = _data(payload)
        assert data["matched_by"] == "player_id"
        assert data["matches"][0]["person"]["display_name"] == "Ali Hassan"

    def test_by_email(self, db_ready):
        payload = server.resolve_person("mona@example.com")
        data = _data(payload)
        assert data["matched_by"] == "email"
        # Mona has no players and no legacy links — empty lists, not errors.
        assert data["matches"][0]["person"]["display_name"] == "Mona Adel"
        assert data["matches"][0]["players"] == []
        assert data["matches"][0]["identities"] == []

    def test_by_phone(self, db_ready):
        payload = server.resolve_person("+965****0001")
        data = _data(payload)
        assert data["matched_by"] == "phone"
        assert data["matches"][0]["person"]["display_name"] == "Ali Hassan"

    def test_unknown_identifier_not_found(self, db_ready):
        payload = server.resolve_person("nobody@nowhere.com")
        body = json.loads(payload)
        assert body["ok"] is False
        assert body["error"] == "not_found"
