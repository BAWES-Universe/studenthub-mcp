"""StudentHub MCP — read-only data layer.

Phase 1 tools (recruitment domain):
  search_candidates, get_candidate_profile
  search_requests, get_request
  get_companies, get_company_tree
  get_universities, get_countries

Safety contract:
  - SELECT-only. No write tools, no DDL, no mutations of any kind.
  - All queries parameterized (built in queries.py).
  - Hard LIMIT on every collection query (default 50, max 200).
  - Designed to run against a dedicated read-only MySQL user in prod;
    today it runs against the local dev clone only.
"""

from __future__ import annotations

import os
import time
from typing import Annotated

import pymysql
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from queries import (
    build_company_tree,
    build_company_tree_sub_companies,
    build_get_candidate_base,
    build_get_candidate_education,
    build_get_candidate_links,
    build_get_candidate_skills,
    build_get_candidate_work,
    build_get_countries,
    build_get_request,
    build_get_request_applications,
    build_get_request_company,
    build_get_universities,
    build_search_candidates,
    build_search_companies,
    build_search_requests,
    clamp_limit,
    err_payload,
    ok_payload,
)

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


def _query(sql: str, params: tuple | None = None) -> list[dict]:
    """Run a read-only SELECT and return rows as dicts."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


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
    limit = clamp_limit(limit)
    sql, params = build_search_candidates(
        query=query, country=country, university=university,
        skill=skill, status=status, limit=limit,
    )
    try:
        rows = _query(sql, params)
    except pymysql.MySQLError as e:
        return err_payload("db_error", f"Query failed: {e}")
    return ok_payload(rows)


@mcp.tool()
def get_candidate_profile(
    candidate_id: Annotated[int, "Candidate id (from search_candidates)"],
) -> str:
    """Full candidate profile: contact details, skills, education, work history.

    Rich view for interview prep and outreach personalization.
    """
    try:
        sql, params = build_get_candidate_base(candidate_id)
        base = _query(sql, params)
        if not base:
            return err_payload("not_found", f"Candidate {candidate_id} not found")

        sql, params = build_get_candidate_skills(candidate_id)
        skills = _query(sql, params)
        sql, params = build_get_candidate_education(candidate_id)
        education = _query(sql, params)
        sql, params = build_get_candidate_work(candidate_id)
        work = _query(sql, params)
        sql, params = build_get_candidate_links(candidate_id)
        links = _query(sql, params)
    except pymysql.MySQLError as e:
        return err_payload("db_error", f"Query failed: {e}")

    return ok_payload(
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
    status: Annotated[str | None, "Pipeline status: cancelled/delivered/finished_by_recruitment/started/re_work"] = None,
    company_id: Annotated[int | None, "Filter by company id (use get_companies for values)"] = None,
    position: Annotated[str | None, "Free-text match on position title"] = None,
    limit: Annotated[int | None, "Max rows (1-200, default 50)"] = None,
) -> str:
    """Search hiring requests (the pipeline). Returns uuid, position, company, status, dates.

    Use for recruiter-velocity triage: what's open, what's stalled, what needs action.
    """
    limit = clamp_limit(limit)
    sql, params = build_search_requests(
        status=status, company_id=company_id, position=position, limit=limit
    )
    try:
        rows = _query(sql, params)
    except pymysql.MySQLError as e:
        return err_payload("db_error", f"Query failed: {e}")
    return ok_payload(rows)


@mcp.tool()
def get_request(
    request_uuid: Annotated[str, "Request uuid (from search_requests)"],
) -> str:
    """Full request detail: position, company, applications (candidates), timeline.

    Use to understand a single hiring pipeline in depth.
    """
    try:
        sql, params = build_get_request(request_uuid)
        base = _query(sql, params)
        if not base:
            return err_payload("not_found", f"Request {request_uuid} not found")

        sql, params = build_get_request_company(base[0].get("company_id"))
        company = _query(sql, params)

        sql, params = build_get_request_applications(request_uuid)
        candidates = _query(sql, params)
    except pymysql.MySQLError as e:
        return err_payload("db_error", f"Query failed: {e}")
    return ok_payload({"request": base[0], "company": company, "applications": candidates})


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
    limit = clamp_limit(limit)
    sql, params = build_search_companies(query=query, country=country, limit=limit)
    try:
        rows = _query(sql, params)
    except pymysql.MySQLError as e:
        return err_payload("db_error", f"Query failed: {e}")
    return ok_payload(rows)


@mcp.tool()
def get_company_tree(
    company_id: Annotated[int, "Company id (use get_companies to find it)"],
) -> str:
    """Company hierarchy: the company, its sub-companies, and the parent (if any).

    Use when rates or invoices need aggregation across sub-companies.
    """
    try:
        sql, params = build_company_tree(company_id)
        base = _query(sql, params)
        if not base:
            return err_payload("not_found", f"Company {company_id} not found")
        node = base[0]
        parent = None
        if node.get("parent_company_id"):
            sql, params = build_company_tree(node["parent_company_id"])
            p = _query(sql, params)
            parent = p[0] if p else None
        sql, params = build_company_tree_sub_companies(company_id)
        subs = _query(sql, params)
    except pymysql.MySQLError as e:
        return err_payload("db_error", f"Query failed: {e}")
    return ok_payload({"company": node, "parent": parent, "sub_companies": subs})


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------


@mcp.tool()
def get_universities(
    country: Annotated[str | None, "Filter by country name"] = None,
    limit: Annotated[int | None, "Max rows (1-200, default 50)"] = None,
) -> str:
    """List universities from the candidate pool. Use to build outreach segments."""
    limit = clamp_limit(limit)
    sql, params = build_get_universities(country=country, limit=limit)
    try:
        rows = _query(sql, params)
    except pymysql.MySQLError as e:
        return err_payload("db_error", f"Query failed: {e}")
    return ok_payload(rows)


@mcp.tool()
def get_countries(limit: Annotated[int | None, "Max rows (1-200, default 50)"] = None) -> str:
    """List countries present in the candidate pool, with counts.

    Use to understand market distribution for campaigns.
    """
    limit = clamp_limit(limit)
    sql, params = build_get_countries(limit=limit)
    try:
        rows = _query(sql, params)
    except pymysql.MySQLError as e:
        return err_payload("db_error", f"Query failed: {e}")
    return ok_payload(rows)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
from starlette.responses import JSONResponse


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
    except Exception:  # noqa: BLE001 - health endpoint must never 500
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
