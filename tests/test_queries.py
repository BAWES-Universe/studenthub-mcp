"""Unit tests for the pure query-building layer (queries.py).

RED phase: these tests fail until queries.py exists with the
build_* functions. No DB connection is needed — they test the
(statement, params) pairs that tools execute.
"""


from queries import (
    build_company_tree,
    build_company_tree_sub_companies,
    build_get_countries,
    build_get_person_identities,
    build_get_person_players,
    build_get_request,
    build_get_request_applications,
    build_resolve_person_by_discord,
    build_resolve_person_by_email,
    build_resolve_person_by_phone,
    build_resolve_person_by_player,
    build_search_candidates,
    build_search_companies,
    build_search_requests,
    clamp_limit,
    err_payload,
    ok_payload,
)

# ---------------------------------------------------------------------------
# clamp_limit
# ---------------------------------------------------------------------------


class TestClampLimit:
    def test_defaults_to_50_when_none(self):
        assert clamp_limit(None) == 50

    def test_clamps_above_max_to_200(self):
        assert clamp_limit(9999) == 200

    def test_clamps_below_min_to_1(self):
        assert clamp_limit(0) == 1
        assert clamp_limit(-5) == 1

    def test_passes_through_valid_value(self):
        assert clamp_limit(37) == 37

    def test_appends_limit_to_sql(self):
        # clamp_limit is used by build_* to append LIMIT — verify builders include it
        pass


# ---------------------------------------------------------------------------
# search_candidates
# ---------------------------------------------------------------------------


class TestBuildSearchCandidates:
    def test_returns_select_with_joins_and_no_filters(self):
        sql, params = build_search_candidates(limit=10)
        assert "FROM candidate c" in sql
        assert "LEFT JOIN country" in sql
        assert "LEFT JOIN university" in sql
        assert params == ()
        assert sql.rstrip().endswith("LIMIT 10")

    def test_query_filter_adds_name_email_phone_clause(self):
        sql, params = build_search_candidates(query="ahmed", limit=10)
        assert "candidate_name LIKE %s" in sql
        assert params.count("%ahmed%") == 3  # name, email, phone

    def test_country_filter_joins_country_name(self):
        sql, params = build_search_candidates(country="Egypt", limit=10)
        assert "country_name_en = %s" in sql
        assert params == ("Egypt",)

    def test_university_filter(self):
        sql, params = build_search_candidates(university="Cairo", limit=10)
        assert "university_name_en LIKE %s" in sql
        assert params == ("%Cairo%",)

    def test_skill_filter_uses_exists_subquery(self):
        sql, params = build_search_candidates(skill="sales", limit=10)
        assert "EXISTS (SELECT 1 FROM candidate_skill cs" in sql
        assert params == ("%sales%",)

    def test_status_filter(self):
        sql, params = build_search_candidates(status=10, limit=10)
        assert "candidate_status = %s" in sql
        assert params == (10,)

    def test_status_zero_is_not_treated_as_falsy(self):
        # Regression: status=0 is a real value (the most common one in prod),
        # so it must add a clause, not be skipped by truthiness.
        sql, params = build_search_candidates(status=0, limit=10)
        assert "candidate_status = %s" in sql
        assert params == (0,)

    def test_combined_filters_all_applied(self):
        sql, params = build_search_candidates(
            query="ali", country="Kuwait", university="K", skill="x", status=1, limit=5
        )
        assert all(
            token in sql
            for token in [
                "candidate_name LIKE %s",
                "country_name_en = %s",
                "university_name_en LIKE %s",
                "EXISTS (SELECT 1 FROM candidate_skill",
                "candidate_status = %s",
            ]
        )
        assert len(params) == 7  # 3 name + 1 country + 1 uni + 1 skill + 1 status


# ---------------------------------------------------------------------------
# search_requests
# ---------------------------------------------------------------------------


class TestBuildSearchRequests:
    def test_basic_select_joins_company(self):
        sql, params = build_search_requests(limit=10)
        assert "FROM request r" in sql
        assert "LEFT JOIN company c" in sql
        assert params == ()
        assert sql.rstrip().endswith("LIMIT 10")

    def test_status_filter(self):
        sql, params = build_search_requests(status="delivered", limit=10)
        assert "request_status = %s" in sql
        assert params == ("delivered",)

    def test_company_filter(self):
        sql, params = build_search_requests(company_id=7, limit=10)
        assert "r.company_id = %s" in sql
        assert params == (7,)

    def test_position_filter(self):
        sql, params = build_search_requests(position="cashier", limit=10)
        assert "request_position_title LIKE %s" in sql
        assert params == ("%cashier%",)


# ---------------------------------------------------------------------------
# get_request
# ---------------------------------------------------------------------------


class TestBuildGetRequest:
    def test_base_query_by_uuid(self):
        sql, params = build_get_request("request_abc")
        assert "FROM request" in sql
        assert "WHERE request_uuid = %s" in sql
        assert params == ("request_abc",)

    def test_applications_query_joins_candidate_and_country(self):
        sql, params = build_get_request_applications("request_abc")
        assert "FROM request_application a" in sql
        assert "LEFT JOIN candidate c" in sql
        assert "LEFT JOIN country co" in sql
        assert "WHERE a.request_uuid = %s" in sql
        assert params == ("request_abc",)


# ---------------------------------------------------------------------------
# companies
# ---------------------------------------------------------------------------


class TestBuildCompanies:
    def test_basic_select_with_parent_and_country_joins(self):
        sql, params = build_search_companies(limit=10)
        assert "FROM company c" in sql
        assert "LEFT JOIN company p" in sql
        assert "LEFT JOIN country co" in sql
        assert params == ()

    def test_query_filter(self):
        sql, params = build_search_companies(query="Azadea", limit=10)
        assert "company_name LIKE %s" in sql
        assert params == ("%Azadea%",)

    def test_country_filter(self):
        sql, params = build_search_companies(country="Kuwait", limit=10)
        assert "country_name_en = %s" in sql
        assert params == ("Kuwait",)


class TestBuildCompanyTree:
    def test_base_lookup(self):
        sql, params = build_company_tree(1)
        assert "WHERE company_id = %s" in sql
        assert params == (1,)

    def test_sub_companies_query(self):
        sql, params = build_company_tree_sub_companies(1)
        assert "WHERE parent_company_id = %s" in sql
        assert params == (1,)


# ---------------------------------------------------------------------------
# reference data
# ---------------------------------------------------------------------------


class TestBuildReference:
    def test_countries_groups_by_country_name(self):
        sql, params = build_get_countries(limit=10)
        assert "GROUP BY co.country_name_en" in sql
        assert "ORDER BY candidate_count DESC" in sql
        assert params == ()
        assert sql.rstrip().endswith("LIMIT 10")


# ---------------------------------------------------------------------------
# payload helpers
# ---------------------------------------------------------------------------


class TestPayloads:
    def test_ok_payload_is_json_with_data(self):
        import json

        p = ok_payload({"a": 1})
        assert json.loads(p) == {"ok": True, "data": {"a": 1}}

    def test_err_payload_is_json_with_code_and_message(self):
        import json

        p = err_payload("db_error", "boom")
        assert json.loads(p) == {"ok": False, "error": "db_error", "message": "boom"}


# ---------------------------------------------------------------------------
# person registry (Layer 2 — resolve_person)
# ---------------------------------------------------------------------------


class TestBuildResolvePerson:
    def test_by_discord_uses_exact_match(self):
        sql, params = build_resolve_person_by_discord("123456789012345678")
        assert "FROM person" in sql
        assert "discord_id = %s" in sql
        assert params == ("123456789012345678",)

    def test_by_player_joins_player_table(self):
        sql, params = build_resolve_person_by_player("player-abc")
        assert "FROM person p" in sql
        assert "JOIN person_player" in sql
        assert "pp.player_id = %s" in sql
        assert params == ("player-abc",)

    def test_by_email_uses_exact_match(self):
        sql, params = build_resolve_person_by_email("ali@example.com")
        assert "FROM person" in sql
        assert "email = %s" in sql
        assert params == ("ali@example.com",)

    def test_by_phone_uses_exact_match(self):
        sql, params = build_resolve_person_by_phone("+965****0001")
        assert "FROM person" in sql
        assert "phone = %s" in sql
        assert params == ("+965****0001",)

    def test_get_person_players_scoped_to_person(self):
        sql, params = build_get_person_players(42)
        assert "FROM person_player" in sql
        assert "person_id = %s" in sql
        assert params == (42,)

    def test_get_person_identities_scoped_to_person(self):
        sql, params = build_get_person_identities(42)
        assert "FROM person_identity" in sql
        assert "person_id = %s" in sql
        assert params == (42,)

    def test_identity_query_selects_account_type_and_legacy_id(self):
        sql, _ = build_get_person_identities(1)
        assert "account_type" in sql
        assert "legacy_id" in sql
        assert "ORDER BY" in sql

