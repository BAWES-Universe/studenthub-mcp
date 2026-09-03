"""Pure query-building layer for the StudentHub MCP.

Every tool's SQL is built here as a (statement, params) pair — no DB
connection, no FastMCP dependency. This makes query construction unit-
testable without a database. server.py executes the built queries.

Safety contract:
  - SELECT-only. No write tools, no DDL, no mutations of any kind.
  - All values parameterized (%s placeholders), never string-interpolated
    into SQL.
  - Hard LIMIT on every collection query (default 50, max 200).

Schema notes (verified against dev clone of prod, 2026-08-11):
  - Legacy Yii2 DB: UUID primary keys (request_uuid, application_uuid),
    snake_case, country/university via FK ids.
  - candidate_country does NOT exist — join country via country_id.
  - request_candidate does NOT exist — it's request_application.
  - request_interview is vestigial (0 rows); fulltimer is legacy/stale and
    deliberately NOT exposed.
"""

from __future__ import annotations

import json
from typing import Any

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def clamp_limit(requested: int | None) -> int:
    """Clamp a requested row limit into [1, MAX_LIMIT]; default 50."""
    if requested is None:
        return DEFAULT_LIMIT
    return max(1, min(int(requested), MAX_LIMIT))


def _append_limit(sql: str, limit: int | None) -> str:
    """Append LIMIT to a SELECT unless the caller explicitly wants none."""
    if limit is None:
        return sql.rstrip().rstrip(";")
    return f"{sql.rstrip().rstrip(';')} LIMIT {int(limit)}"


def ok_payload(data: Any) -> str:
    """JSON success envelope used by every tool."""
    return json.dumps({"ok": True, "data": data}, default=str)


def err_payload(code: str, message: str) -> str:
    """JSON error envelope used by every tool."""
    return json.dumps({"ok": False, "error": code, "message": message})


def _where(clauses: list[str], params: list[Any]) -> tuple[str, tuple[Any, ...]]:
    """Build ' WHERE ...' fragment + tuple params from collected clauses."""
    if not clauses:
        return "", ()
    return " WHERE " + " AND ".join(clauses), tuple(params)


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


def build_search_candidates(
    query: str | None = None,
    country: str | None = None,
    university: str | None = None,
    skill: str | None = None,
    status: Any | None = None,
    limit: int | None = None,
) -> tuple[str, tuple[Any, ...]]:
    """SELECT over candidates with optional filters; returns (sql, params)."""
    limit = clamp_limit(limit)
    clauses: list[str] = []
    params: list[Any] = []

    if query:
        like = f"%{query}%"
        clauses.append(
            "(c.candidate_name LIKE %s OR c.candidate_email LIKE %s OR c.candidate_phone LIKE %s)"
        )
        params.extend([like, like, like])
    if country:
        clauses.append("co.country_name_en = %s")
        params.append(country)
    if university:
        clauses.append("u.university_name_en LIKE %s")
        params.append(f"%{university}%")
    if skill:
        clauses.append(
            "EXISTS (SELECT 1 FROM candidate_skill cs WHERE cs.candidate_id = c.candidate_id "
            "AND cs.skill LIKE %s AND cs.deleted = 0)"
        )
        params.append(f"%{skill}%")
    if status is not None:
        clauses.append("c.candidate_status = %s")
        params.append(status)

    where, p = _where(clauses, params)
    sql = f"""
        SELECT c.candidate_id, c.candidate_name, c.candidate_email, c.candidate_phone,
               co.country_name_en AS candidate_country, u.university_name_en AS candidate_university,
               c.candidate_status, c.candidate_created_at
        FROM candidate c
        LEFT JOIN country co ON c.country_id = co.country_id
        LEFT JOIN university u ON c.university_id = u.university_id
        {where}
        ORDER BY c.candidate_created_at DESC
    """
    return _append_limit(sql, limit), p


def build_get_candidate_base(candidate_id: int) -> tuple[str, tuple[Any, ...]]:
    """Full candidate row joined with country/university names."""
    sql = """
        SELECT c.*, co.country_name_en AS candidate_country, u.university_name_en AS candidate_university
        FROM candidate c
        LEFT JOIN country co ON c.country_id = co.country_id
        LEFT JOIN university u ON c.university_id = u.university_id
        WHERE c.candidate_id = %s
    """
    return sql, (candidate_id,)


def build_get_candidate_skills(candidate_id: int) -> tuple[str, tuple[Any, ...]]:
    sql = (
        "SELECT * FROM candidate_skill WHERE candidate_id = %s AND deleted = 0 "
        "ORDER BY candidate_skill_id"
    )
    return sql, (candidate_id,)


def build_get_candidate_education(candidate_id: int) -> tuple[str, tuple[Any, ...]]:
    sql = """
        SELECT e.*, u.university_name_en, u.university_name_ar
        FROM candidate_education e
        LEFT JOIN university u ON e.university_id = u.university_id
        WHERE e.candidate_id = %s ORDER BY e.graduation_year DESC
    """
    return sql, (candidate_id,)


def build_get_candidate_work(candidate_id: int) -> tuple[str, tuple[Any, ...]]:
    sql = """
        SELECT w.*, c.company_name, c.parent_company_id
        FROM candidate_work_history w
        LEFT JOIN company c ON w.company_id = c.company_id
        WHERE w.candidate_id = %s AND w.deleted = 0 ORDER BY w.start_date DESC
    """
    return sql, (candidate_id,)


def build_get_candidate_links(candidate_id: int) -> tuple[str, tuple[Any, ...]]:
    sql = "SELECT * FROM candidate_link WHERE candidate_id = %s ORDER BY created_at DESC"
    return sql, (candidate_id,)


# ---------------------------------------------------------------------------
# Requests (hiring pipeline)
# ---------------------------------------------------------------------------


def build_search_requests(
    status: str | None = None,
    company_id: int | None = None,
    position: str | None = None,
    limit: int | None = None,
) -> tuple[str, tuple[Any, ...]]:
    """SELECT over the hiring pipeline with optional filters; returns (sql, params)."""
    limit = clamp_limit(limit)
    clauses: list[str] = []
    params: list[Any] = []

    if status:
        clauses.append("r.request_status = %s")
        params.append(status)
    if company_id:
        clauses.append("r.company_id = %s")
        params.append(company_id)
    if position:
        clauses.append("r.request_position_title LIKE %s")
        params.append(f"%{position}%")

    where, p = _where(clauses, params)
    sql = f"""
        SELECT r.request_uuid, r.request_position_title, r.request_status,
               r.company_id, c.company_name,
               r.request_created_datetime, r.request_started_at, r.request_delivered_at,
               r.request_priority, r.request_number_of_employees
        FROM request r
        LEFT JOIN company c ON r.company_id = c.company_id
        {where}
        ORDER BY r.request_created_datetime DESC
    """
    return _append_limit(sql, limit), p


def build_get_request(request_uuid: str) -> tuple[str, tuple[Any, ...]]:
    """Full request row by uuid."""
    sql = "SELECT * FROM request WHERE request_uuid = %s"
    return sql, (request_uuid,)


def build_get_request_company(company_id: int | None) -> tuple[str, tuple[Any, ...]]:
    sql = (
        "SELECT company_id, company_name, company_common_name_en FROM company "
        "WHERE company_id = %s"
    )
    return sql, (company_id,)


def build_get_request_applications(request_uuid: str) -> tuple[str, tuple[Any, ...]]:
    """Candidates applied to a request, with country names."""
    sql = """
        SELECT a.application_uuid, a.candidate_id, a.status AS application_status,
               c.candidate_name, c.candidate_email, c.candidate_phone,
               co.country_name_en AS candidate_country
        FROM request_application a
        LEFT JOIN candidate c ON a.candidate_id = c.candidate_id
        LEFT JOIN country co ON c.country_id = co.country_id
        WHERE a.request_uuid = %s
        ORDER BY a.created_at DESC
    """
    return sql, (request_uuid,)


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------


def build_search_companies(
    query: str | None = None,
    country: str | None = None,
    limit: int | None = None,
) -> tuple[str, tuple[Any, ...]]:
    """SELECT over companies with optional filters; returns (sql, params)."""
    limit = clamp_limit(limit)
    clauses: list[str] = []
    params: list[Any] = []

    if query:
        clauses.append("c.company_name LIKE %s")
        params.append(f"%{query}%")
    if country:
        clauses.append("co.country_name_en = %s")
        params.append(country)

    where, p = _where(clauses, params)
    sql = f"""
        SELECT c.company_id, c.company_name, co.country_name_en AS company_country,
               c.parent_company_id, p.company_name AS parent_company_name,
               c.company_hourly_rate, c.company_approved_to_hire, c.company_status_override
        FROM company c
        LEFT JOIN company p ON c.parent_company_id = p.company_id
        LEFT JOIN country co ON c.country_id = co.country_id
        {where}
        ORDER BY c.company_name
    """
    return _append_limit(sql, limit), p


def build_company_tree(company_id: int) -> tuple[str, tuple[Any, ...]]:
    """Look up a single company node by id."""
    sql = "SELECT company_id, company_name, parent_company_id FROM company WHERE company_id = %s"
    return sql, (company_id,)


def build_company_tree_sub_companies(company_id: int) -> tuple[str, tuple[Any, ...]]:
    """All sub-companies of a parent (direct children only)."""
    sql = (
        "SELECT company_id, company_name, parent_company_id FROM company "
        "WHERE parent_company_id = %s ORDER BY company_name"
    )
    return sql, (company_id,)


# ---------------------------------------------------------------------------
# Person registry (Layer 2 — resolve_person)
#
# One person row per human, linking cross-platform identifiers to legacy
# StudentHub account IDs. ADDITIVE — these tables are created by
# migrations/001_person_registry.sql and touched by no legacy code.
# The MCP is SELECT-only: these builders read the registry, never write.
# ---------------------------------------------------------------------------


def build_resolve_person_by_discord(discord_id: str) -> tuple[str, tuple[Any, ...]]:
    """Person row by exact Discord user id (unique)."""
    sql = "SELECT * FROM person WHERE discord_id = %s"
    return sql, (discord_id,)


def build_resolve_person_by_player(player_id: str) -> tuple[str, tuple[Any, ...]]:
    """Person row via Universe player id (one player belongs to one person)."""
    sql = """
        SELECT p.*
        FROM person p
        JOIN person_player pp ON pp.person_id = p.person_id
        WHERE pp.player_id = %s
    """
    return sql, (player_id,)


def build_resolve_person_by_email(email: str) -> tuple[str, tuple[Any, ...]]:
    """Person rows by exact email (non-unique — a shared mailbox may match many)."""
    sql = "SELECT * FROM person WHERE email = %s ORDER BY person_id"
    return sql, (email,)


def build_resolve_person_by_phone(phone: str) -> tuple[str, tuple[Any, ...]]:
    """Person rows by exact phone (non-unique)."""
    sql = "SELECT * FROM person WHERE phone = %s ORDER BY person_id"
    return sql, (phone,)


def build_get_person_players(person_id: int) -> tuple[str, tuple[Any, ...]]:
    """All Universe player accounts linked to a person."""
    sql = "SELECT player_id FROM person_player WHERE person_id = %s ORDER BY created_at"
    return sql, (person_id,)


def build_get_person_identities(person_id: int) -> tuple[str, tuple[Any, ...]]:
    """All legacy StudentHub account links for a person (account_type, legacy_id)."""
    sql = (
        "SELECT account_type, legacy_id FROM person_identity "
        "WHERE person_id = %s ORDER BY account_type, legacy_id"
    )
    return sql, (person_id,)


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------


def build_get_universities(
    country: str | None = None,
    limit: int | None = None,
) -> tuple[str, tuple[Any, ...]]:
    """Universities with candidate counts; optional country filter."""
    limit = clamp_limit(limit)
    clauses: list[str] = []
    params: list[Any] = []

    if country:
        clauses.append("co.country_name_en = %s")
        params.append(country)

    where, p = _where(clauses, params)
    sql = f"""
        SELECT u.university_id, u.university_name_en, u.university_name_ar,
               (SELECT COUNT(*) FROM candidate c WHERE c.university_id = u.university_id) AS candidate_count
        FROM university u
        LEFT JOIN country co ON u.university_country_id = co.country_id
        {where}
        ORDER BY u.university_name_en
    """
    return _append_limit(sql, limit), p


def build_get_countries(limit: int | None = None) -> tuple[str, tuple[Any, ...]]:
    """Country distribution of the candidate pool."""
    limit = clamp_limit(limit)
    sql = """
        SELECT co.country_name_en AS country, COUNT(*) AS candidate_count
        FROM candidate c
        JOIN country co ON c.country_id = co.country_id
        GROUP BY co.country_name_en
        ORDER BY candidate_count DESC
    """
    return _append_limit(sql, limit), ()
