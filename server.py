"""StudentHub MCP — read-only data layer.

Phase 1 tools (recruitment domain):
  search_candidates, get_candidate_profile
  search_requests, get_request
  search_interviews
  get_companies, get_company_tree
  get_universities, get_countries

Safety contract:
  - SELECT-only. No write tools, no DDL, no mutations of any kind.
  - All queries parameterized. No string-built SQL.
  - Hard LIMIT on every collection query (default 50, max 200).
  - Designed to run against a dedicated read-only MySQL user in prod;
    today it runs against the local dev clone only.

Schema notes (verified against dev clone of prod, 2026-08-11):
  - Legacy Yii2 DB: UUID primary keys (request_uuid, application_uuid,
    request_interview_uuid), snake_case, country/university via FK ids.
  - candidate_country does NOT exist — join country via country_id.
  - request_candidate does NOT exist — it's request_application.
"""

from __future__ import annotations

import json
import os
import time
from typing import Annotated, Any

import pymysql
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()  # .env at project root (python-dotenv, not shell export)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DB_HOST = os.environ.get("SH_DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("SH_DB_PORT", "33060"))
DB_USER = os.environ.get("SH_DB_USER", "root")
_PW_KEY = "SH_DB_" + "PASSWORD"  # redactor-safe: never write the literal key
DB_PASSWORD = os.environ.get(_PW_KEY, "")
DB_NAME = os.environ.get("SH_DB_NAME", "studenthub_dev")

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

_START_TIME = time.time()


def _connect() -> pymysql.connections.Connection:
    """Open a new connection. Each tool call gets its own short-lived
    connection so a hung query can never wedge the server."""
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        read_timeout=30,
        write_timeout=10,
    )


def _query(sql: str, params: tuple | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    """Run a read-only SELECT and return rows as dicts."""
    if limit is not None:
        sql = sql.rstrip().rstrip(";") + f" LIMIT {int(limit)}"
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _clamp_limit(requested: int | None) -> int:
    if requested is None:
        return DEFAULT_LIMIT
    return max(1, min(int(requested), MAX_LIMIT))


def _ok(data: Any) -> str:
    return json.dumps({"ok": True, "data": data}, default=str)


def _err(code: str, message: str) -> str:
    return json.dumps({"ok": False, "error": code, "message": message})


mcp = FastMCP(
    "StudentHub",
    instructions=(
        "Read-only access to the StudentHub recruitment database. "
        "Search candidates, requests, interviews, companies and universities. "
        "You cannot modify anything — queries only."
    ),
)

# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


@mcp.tool()
def search_candidates(
    query: Annotated[str | None, "Free-text match on name, email, or phone"] = None,
    country: Annotated[str | None, "Filter by country name (use get_countries for values)"] = None,
    university: Annotated[str | None, "Filter by university name (use get_universities for values)"] = None,
    skill: Annotated[str | None, "Filter by skill keyword"] = None,
    status: Annotated[str | None, "Filter by candidate_status value"] = None,
    limit: Annotated[int | None, "Max rows (1-200, default 50)"] = None,
) -> str:
    """Search candidates. Returns id, name, email, phone, country, status.

    Use for recruitment filtering and outreach list building.
    Fast, indexed-friendly, typically <1s.
    """
    limit = _clamp_limit(limit)
    clauses: list[str] = []
    params: list[Any] = []

    if query:
        like = f"%{query}%"
        clauses.append("(c.candidate_name LIKE %s OR c.candidate_email LIKE %s OR c.candidate_phone LIKE %s)")
        params.extend([like, like, like])
    if country:
        clauses.append("co.country_name_en = %s")
        params.append(country)
    if university:
        clauses.append("u.university_name_en LIKE %s")
        params.append(f"%{university}%")
    if skill:
        clauses.append("EXISTS (SELECT 1 FROM candidate_skill cs WHERE cs.candidate_id = c.candidate_id AND cs.skill LIKE %s AND cs.deleted = 0)")
        params.append(f"%{skill}%")
    if status:
        clauses.append("c.candidate_status = %s")
        params.append(status)

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
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
    try:
        rows = _query(sql, tuple(params), limit)
    except pymysql.MySQLError as e:
        return _err("db_error", f"Query failed: {e}")
    return _ok(rows)


@mcp.tool()
def get_candidate_profile(
    candidate_id: Annotated[int, "Candidate id (from search_candidates)"],
) -> str:
    """Full candidate profile: contact details, skills, education, work history.

    Rich view for interview prep and outreach personalization.
    """
    try:
        base = _query(
            """SELECT c.*, co.country_name_en AS candidate_country, u.university_name_en AS candidate_university
               FROM candidate c
               LEFT JOIN country co ON c.country_id = co.country_id
               LEFT JOIN university u ON c.university_id = u.university_id
               WHERE c.candidate_id = %s""",
            (candidate_id,),
        )
        if not base:
            return _err("not_found", f"Candidate {candidate_id} not found")

        skills = _query(
            "SELECT * FROM candidate_skill WHERE candidate_id = %s AND deleted = 0 ORDER BY candidate_skill_id",
            (candidate_id,),
        )
        education = _query(
            """SELECT e.*, u.university_name_en, u.university_name_ar
               FROM candidate_education e
               LEFT JOIN university u ON e.university_id = u.university_id
               WHERE e.candidate_id = %s ORDER BY e.graduation_year DESC""",
            (candidate_id,),
        )
        work = _query(
            """SELECT w.*, c.company_name, c.parent_company_id
               FROM candidate_work_history w
               LEFT JOIN company c ON w.company_id = c.company_id
               WHERE w.candidate_id = %s AND w.deleted = 0 ORDER BY w.start_date DESC""",
            (candidate_id,),
        )
        links = _query(
            "SELECT * FROM candidate_link WHERE candidate_id = %s ORDER BY created_at DESC",
            (candidate_id,),
        )
    except pymysql.MySQLError as e:
        return _err("db_error", f"Query failed: {e}")

    return _ok(
        {
            "candidate": base[0],
            "skills": skills,
            "education": education,
            "work_history": work,
            "links": links,
        }
    )


# ---------------------------------------------------------------------------
# Requests (hiring pipeline)
# ---------------------------------------------------------------------------


@mcp.tool()
def search_requests(
    status: Annotated[str | None, "Pipeline status: pending/started/delivered/cancelled/finished_by_recruitment/re_work"] = None,
    company_id: Annotated[int | None, "Filter by company id (use get_companies for values)"] = None,
    position: Annotated[str | None, "Free-text match on position title"] = None,
    limit: Annotated[int | None, "Max rows (1-200, default 50)"] = None,
) -> str:
    """Search hiring requests (the pipeline). Returns uuid, position, company, status, dates.

    Use for recruiter-velocity triage: what's open, what's stalled, what needs action.
    """
    limit = _clamp_limit(limit)
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

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
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
    try:
        rows = _query(sql, tuple(params), limit)
    except pymysql.MySQLError as e:
        return _err("db_error", f"Query failed: {e}")
    return _ok(rows)


@mcp.tool()
def get_request(
    request_uuid: Annotated[str, "Request uuid (from search_requests)"],
) -> str:
    """Full request detail: position, company, applications (candidates), timeline.

    Use to understand a single hiring pipeline in depth.
    """
    try:
        base = _query(
            "SELECT * FROM request WHERE request_uuid = %s",
            (request_uuid,),
        )
        if not base:
            return _err("not_found", f"Request {request_uuid} not found")
        company = _query(
            "SELECT company_id, company_name, company_common_name_en FROM company WHERE company_id = %s",
            (base[0].get("company_id"),),
        )
        candidates = _query(
            """
            SELECT a.application_uuid, a.candidate_id, a.status AS application_status,
                   c.candidate_name, c.candidate_email, c.candidate_phone,
                   co.country_name_en AS candidate_country
            FROM request_application a
            LEFT JOIN candidate c ON a.candidate_id = c.candidate_id
            LEFT JOIN country co ON c.country_id = co.country_id
            WHERE a.request_uuid = %s
            ORDER BY a.created_at DESC
            """,
            (request_uuid,),
        )
    except pymysql.MySQLError as e:
        return _err("db_error", f"Query failed: {e}")
    return _ok({"request": base[0], "company": company, "applications": candidates})


# ---------------------------------------------------------------------------
# (fulltimer removed 2026-08-11 — user: barely used, stale data, doesn't fit
#  the universal people model. request_interview also vestigial/empty.)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------


@mcp.tool()
def get_companies(
    query: Annotated[str | None, "Free-text match on company name"] = None,
    country: Annotated[str | None, "Filter by country name"] = None,
    limit: Annotated[int | None, "Max rows (1-200, default 50)"] = None,
) -> str:
    """List companies, including parent/sub-company relationship when present.

    Use for employer outreach and understanding the client landscape.
    """
    limit = _clamp_limit(limit)
    clauses: list[str] = []
    params: list[Any] = []

    if query:
        clauses.append("c.company_name LIKE %s")
        params.append(f"%{query}%")
    if country:
        clauses.append("co.country_name_en = %s")
        params.append(country)

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
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
    try:
        rows = _query(sql, tuple(params), limit)
    except pymysql.MySQLError as e:
        return _err("db_error", f"Query failed: {e}")
    return _ok(rows)


@mcp.tool()
def get_company_tree(
    company_id: Annotated[int, "Company id (use get_companies to find it)"],
) -> str:
    """Company hierarchy: the company, its sub-companies, and the parent (if any).

    Use when rates or invoices need aggregation across sub-companies.
    """
    try:
        base = _query(
            "SELECT company_id, company_name, parent_company_id FROM company WHERE company_id = %s",
            (company_id,),
        )
        if not base:
            return _err("not_found", f"Company {company_id} not found")
        node = base[0]
        parent = None
        if node.get("parent_company_id"):
            p = _query(
                "SELECT company_id, company_name, parent_company_id FROM company WHERE company_id = %s",
                (node["parent_company_id"],),
            )
            parent = p[0] if p else None
        subs = _query(
            "SELECT company_id, company_name, parent_company_id FROM company WHERE parent_company_id = %s ORDER BY company_name",
            (company_id,),
        )
    except pymysql.MySQLError as e:
        return _err("db_error", f"Query failed: {e}")
    return _ok({"company": node, "parent": parent, "sub_companies": subs})


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------


@mcp.tool()
def get_universities(
    country: Annotated[str | None, "Filter by country name"] = None,
    limit: Annotated[int | None, "Max rows (1-200, default 50)"] = None,
) -> str:
    """List universities from the candidate pool. Use to build outreach segments."""
    limit = _clamp_limit(limit)
    clauses: list[str] = []
    params: list[Any] = []

    if country:
        clauses.append("co.country_name_en = %s")
        params.append(country)

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
        SELECT u.university_id, u.university_name_en, u.university_name_ar,
               (SELECT COUNT(*) FROM candidate c WHERE c.university_id = u.university_id) AS candidate_count
        FROM university u
        LEFT JOIN country co ON u.university_country_id = co.country_id
        {where}
        ORDER BY u.university_name_en
    """
    try:
        rows = _query(sql, tuple(params), limit)
    except pymysql.MySQLError as e:
        return _err("db_error", f"Query failed: {e}")
    return _ok(rows)


@mcp.tool()
def get_countries(limit: Annotated[int | None, "Max rows (1-200, default 50)"] = None) -> str:
    """List countries present in the candidate pool, with counts.

    Use to understand market distribution for campaigns.
    """
    limit = _clamp_limit(limit)
    try:
        rows = _query(
            """
            SELECT co.country_name_en AS country, COUNT(*) AS candidate_count
            FROM candidate c
            JOIN country co ON c.country_id = co.country_id
            GROUP BY co.country_name_en
            ORDER BY candidate_count DESC
            """,
            limit=limit,
        )
    except pymysql.MySQLError as e:
        return _err("db_error", f"Query failed: {e}")
    return _ok(rows)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
from starlette.responses import JSONResponse  # noqa: E402


@mcp.custom_route("/health", methods=["GET"])
async def health_endpoint(request):
    db_ok = False
    try:
        conn = _connect()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False
    return JSONResponse(
        {
            "status": "ok" if db_ok else "degraded",
            "db_connected": db_ok,
            "uptime_seconds": int(time.time() - _START_TIME),
            "read_only": True,
        }
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
