"""The 13 Hirist endpoints. Every path is served with and without the
`/hirist` prefix, so code generated against the hosted API on RapidAPI
(paths like /jobs/details) runs unchanged against this server.

Params are validated by the same marshmallow schemas the hosted API uses
(hirist/schemas.py), and responses carry the same pagination block."""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from hirist import companies, jobs, lookups, recruiters
from hirist import schemas as S
from schema_fields import load_query
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The request query as unicode strings (bottle 0.12's .get() hands back
    latin-1 decoded bytes, so a UTF-8 "Bengaluru" with accents would break)."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _page_link(path, params, page):
    if not page:
        return None
    host = request.headers.get("Host") or "localhost:8000"
    scheme = request.urlparts.scheme or "http"
    query = {k: v for k, v in params.items() if v not in (None, "", False)}
    query["page"] = page
    return f"{scheme}://{host}{path}?{urlencode(query, doseq=True)}"


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def paginate(result, path, params):
    """Lift the scraper's `pagination` block into the flat shape the hosted
    API returns: count / per_page / current_page / total_pages / next / previous."""
    pagination = result.pop("pagination", None) or {}
    result.pop("count", None)
    page = _as_int(pagination.get("page")) or _as_int(params.get("page")) or 1
    total_pages = max(_as_int(pagination.get("total_pages")), 0)
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(path, params, page + 1 if page < total_pages else None),
        "previous": _page_link(path, params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def call(schema, fn, path, paginated=False):
    """Validate the query, run the scraper, map failures to HTTP:
    bad params -> 400, missing job / company / recruiter -> 404,
    blocks / upstream failures -> 502, anything else -> 500."""
    params = query_dict()
    data, error = load_query(schema, params)
    if error:
        return json_response(error, 400)
    try:
        result = fn(**data)
    except ValueError as e:
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:
        return json_response({"error": f"hirist rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except (Blocked, UpstreamError) as e:
        return json_response({"error": f"hirist {path.strip('/')} failed: {e}"}, 502)
    except Exception as e:
        return json_response({"error": f"hirist {path.strip('/')} failed: {type(e).__name__}: {e}"}, 500)
    if paginated:
        result = paginate(result, request.path, params)
    return json_response(result)


def mount(path, schema, fn, paginated=False):
    """Serve one endpoint at /path and /hirist/path."""
    def handler():
        return call(schema, fn, path, paginated)
    handler.__name__ = "hirist_" + path.strip("/").replace("/", "_").replace("-", "_")
    route(path, method="GET")(handler)
    route("/hirist" + path, method="GET")(handler)


ENDPOINTS = [
    ("/jobs/details", S.JobSchema, jobs.details, False),
    ("/jobs/search", S.JobSearchSchema, jobs.search, True),
    ("/jobs/batch", S.JobBatchSchema, jobs.batch, False),
    ("/jobs/similar", S.SimilarJobsSchema, jobs.similar, False),
    ("/companies/details", S.CompanySchema, companies.details, False),
    ("/companies/jobs", S.CompanyJobsSchema, companies.open_jobs, True),
    ("/companies/search", S.CompanySearchSchema, companies.search, True),
    ("/recruiters/details", S.RecruiterSchema, recruiters.details, False),
    ("/recruiters/jobs", S.RecruiterJobsSchema, recruiters.open_jobs, True),
    ("/autocomplete", S.AutocompleteSchema, lookups.autocomplete, False),
    ("/skills", S.SkillsSchema, lookups.skills, False),
    ("/categories", S.EmptySchema, lookups.categories, False),
    ("/locations", S.EmptySchema, lookups.locations, False),
]

for _path, _schema, _fn, _paginated in ENDPOINTS:
    mount(_path, _schema, _fn, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, *_ in ENDPOINTS]})
