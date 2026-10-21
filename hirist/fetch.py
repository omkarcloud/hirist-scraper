"""hirist.tech transport: plain curl_cffi, no browser, validated 2026-10-19
from a direct India egress with no cookies and no login.

The site is a Next.js shell; every listing comes from its job service at
gladiator.hirist.tech/job, which answers an anonymous client (header
`version: 2`, the one the site's own bundle sends). Surfaces:

  search(params)                /search?query=&page=&size=&loc=&minexp=&maxexp=
                                &posting=&categoryId= — the free-text search
                                (totalJobs, totalPages, hasMore; `size` up
                                to 100). An empty query is a 404 upstream.
  keyword_feed(params)          /keyword/?keywordId=&categoryId=&loc=&… — the
                                skill feed; without keywordId it is the whole
                                board (every open job, newest first), which
                                is how filters without a text query run.
  category_feed(params)         /category/?categoryId=&… — the category feed
                                (categoryId is mandatory upstream).
  job_detail(id)                /detail?jobcode= — the full ad: description
                                HTML, skills with mandatory flags, salary,
                                recruiter, the company's AmbitionBox profile,
                                application / recruiter-action counts,
                                hasExpired / permanentlyRemoved (removed ads
                                still answer). Unknown id -> JOB_NOT_FOUND.
  similar_jobs(id, tag_ids)     /similarjobs?jobcode=&tags= — up to 50.
  tags()                        /tags — every skill tag by category with its
                                live job count (~320 KB).
  tag_info(slug)                /taginfo?slug= — one tag by its /k/ slug.
  suggest(query)                /search/keyword?query= — the search box.
  company_list(page, params)    /company-list?page=&loc=&catId= — the company
                                directory, 50 a page (the page's own count is
                                the only total: numFound == len(docs)).
  company_search(keyword, …)    /company-list/search?keyword= — companies by
                                name (numFound = the total, one page).
  company_data(slug)            /company-data?slug= — the AmbitionBox profile
                                ({} for a company without one).
  company_jobs(slug, ids, page) /top-jobs?slug=&companyId=|cid=&page= — a
                                company's open jobs, 15 a page, `count` total.
  company_slugs()               /companies/slugs — every company page slug
                                with its name (~25k rows, 1.5 MB).
  recruiter(id)                 /data/recruiter?id= — the recruiter profile
                                (an unknown id is a 500 upstream -> NotFound).
  recruiter_jobs(id, page)      /recruiterfeed/?recruiterId=&page= — 20 a page.

Logged out, /detail masks applyCount / hits / recruiterName as '*****'
(the feeds still carry the counts). /jobfeed and /insights need a login and
are not used.

Egress: config.hirist_proxy() — in the hosted service every call rides a
sticky residential exit (hirist never sees the server's own IP), one exit
per thread reused until a call fails; a 429 / 403 / 5xx retries on a fresh
exit. No rate limit or challenge was seen (the Apify actors on the same
backend report the same). The standalone package's config returns its
HIRIST_PROXY env var or None (direct, your own IP). The patchright click-through
(indeed/fetch.py _browser_page) is the escalation if a challenge ever
appears — not built while plain HTTP works.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  HiristUpstreamError  transport failure / 5xx / unexpected body — retryable
  HiristBlocked        429 / 403 / challenge                     — retryable on a new exit
  HiristBadRequest     the site rejected the params (400)        — never retried
  HiristNotFound       no such job / company / recruiter         — never retried
"""
import json
import os
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from hirist import refdata

IMPERSONATE = "chrome"
TIMEOUT = (10, 60)            # (connect, read) — /tags and /companies/slugs are big

JSON_HEADERS = {"accept": "application/json, text/plain, */*", "accept-language": "en-US,en;q=0.9",
                "origin": refdata.BASE_URL, "referer": refdata.BASE_URL + "/", "version": "2"}
CF_MARKERS = ("just a moment", "challenge-error-text", "cf-chl", "challenge-platform", "attention required")

SEARCH_PATH = "/search"
KEYWORD_PATH = "/keyword/"
CATEGORY_PATH = "/category/"
DETAIL_PATH = "/detail"
SIMILAR_PATH = "/similarjobs"
TAGS_PATH = "/tags"
TAG_INFO_PATH = "/taginfo"
SUGGEST_PATH = "/search/keyword"
COMPANY_LIST_PATH = "/company-list"
COMPANY_SEARCH_PATH = "/company-list/search"
COMPANY_DATA_PATH = "/company-data"
COMPANY_JOBS_PATH = "/top-jobs"
COMPANY_SLUGS_PATH = "/companies/slugs"
RECRUITER_PATH = "/data/recruiter"
RECRUITER_JOBS_PATH = "/recruiterfeed/"


class HiristUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unexpected body — retryable."""


class HiristBlocked(HiristUpstreamError, Blocked):
    """429 / 403 / challenge — retryable on a fresh exit."""


class HiristBadRequest(BadRequest):
    """The site rejected the params — never retried."""


class HiristNotFound(NotFound):
    """No such job / company / recruiter — never retried."""


def dump_debug(name, text):
    """Write a raw response to $HIRIST_DEBUG_DIR/<name>.txt for post-mortems."""
    dbg = os.environ.get("HIRIST_DEBUG_DIR", "")
    if dbg and text:
        try:
            os.makedirs(dbg, exist_ok=True)
            with open(os.path.join(dbg, name + ".txt"), "w") as f:
                f.write(text)
        except OSError:
            pass


# ---- curl sessions (per thread, keyed by exit) ---------------------------------------------------

_local = threading.local()


def _sessions():
    store = getattr(_local, "sessions", None)
    if store is None:
        store = _local.sessions = OrderedDict()
    return store


def _session(key, proxy):
    from curl_cffi import requests as curl_requests
    store = _sessions()
    sess = store.get(key)
    if sess is None:
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        store[key] = sess
        while len(store) > 4:
            _, old = store.popitem(last=False)
            try:
                old.close()
            except Exception:
                pass
    else:
        store.move_to_end(key)
    return sess


def _drop_session(key):
    sess = _sessions().pop(key, None)
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _exit(fresh=False):
    """(session key, proxy) for this thread: one sticky exit reused call
    after call (its curl session keeps the connection warm), a fresh one
    after a failure. config.hirist_proxy() None = direct (the standalone
    package run on your own machine)."""
    held = getattr(_local, "exit", None)
    if held is None or fresh:
        proxy = config.hirist_proxy(fallback=fresh)
        held = (f"{proxy or 'direct'}", proxy)
        _local.exit = held
    return held


def _attempts(label, send):
    """Run send(session) under the retry policy: HiristUpstreamError (incl.
    Blocked) retries on a fresh exit up to config.HIRIST_MAX_ATTEMPTS
    times; BadRequest / NotFound surface at once."""
    attempts = max(1, int(config.HIRIST_MAX_ATTEMPTS))
    last = None
    for attempt in range(1, attempts + 1):
        key, proxy = _exit(fresh=attempt > 1)
        sess = _session(key, proxy)
        try:
            return send(sess)
        except (HiristBadRequest, HiristNotFound):
            raise
        except HiristUpstreamError as e:
            last = e
        except Exception as e:
            last = HiristUpstreamError(f"request failed on {label}: {type(e).__name__}: {e}")
        _drop_session(key)
        _local.exit = None          # the next attempt (and call) takes a fresh exit
        print(f"hirist: attempt {attempt}/{attempts} on {label} failed: {last}")
        if attempt < attempts:
            time.sleep(1.0 * attempt)
    raise last


def is_challenged(status, headers, text):
    if (headers or {}).get("cf-mitigated") == "challenge":
        return True
    head = (text or "")[:4000].lower()
    return status in (403, 429, 503) and any(m in head for m in CF_MARKERS)


def _error_message(body, text):
    """The backend's error body is {"error": {"statusCode", "name", "message"}}."""
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        err = body["error"]
        return f"{err.get('name') or 'error'}: {err.get('message') or ''}".strip(": ")
    return (text or "")[:200]


def _classify(resp, label, missing_on_500=False):
    """Raise the failure a response represents, else return its JSON.
    `missing_on_500`: the endpoint answers a bare 500 for an unknown id."""
    status = resp.status_code
    headers = dict(resp.headers)
    text = resp.text or ""
    if is_challenged(status, headers, text):
        dump_debug("challenged", text)
        raise HiristBlocked(f"challenge (HTTP {status}) on {label}")
    if status in (403, 429):
        raise HiristBlocked(f"HTTP {status} on {label}")
    try:
        body = json.loads(text) if text else None
    except ValueError:
        body = None
    if status in (404, 410):
        raise HiristNotFound(f"hirist has no record for {label}")
    if status == 400:
        raise HiristBadRequest(f"hirist rejected the request on {label}: {_error_message(body, text)}")
    if status == 500 and missing_on_500 and "Internal Server Error" in _error_message(body, text):
        raise HiristNotFound(f"hirist has no record for {label}")
    if status >= 500:
        raise HiristUpstreamError(f"HTTP {status} on {label}: {_error_message(body, text)}")
    if status != 200:
        raise HiristUpstreamError(f"HTTP {status} on {label}")
    if body is None:
        dump_debug("non_json", text)
        raise HiristUpstreamError(f"non-JSON answer on {label}")
    # the service answers 200 with an {"error": {...}} body for some failures
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        code = body["error"].get("statusCode")
        name = str(body["error"].get("name") or "")
        if code == 404 or "NOT_FOUND" in name:
            raise HiristNotFound(f"hirist has no record for {label}")
        if code == 401:
            raise HiristBadRequest(f"hirist needs a login for {label}")
        if code == 400:
            raise HiristBadRequest(f"hirist rejected the request on {label}: {_error_message(body, text)}")
        raise HiristUpstreamError(f"{_error_message(body, text)} on {label}")
    return body


def api_get(path, params=None, label=None, expect=dict, missing_on_500=False):
    """GET one endpoint of the job service -> its parsed body (`expect` =
    the body type: dict / list)."""
    query = {k: v for k, v in (params or {}).items() if v not in (None, "", [])}
    url = f"{refdata.API_URL}{path}" + (f"?{urlencode(query, doseq=True)}" if query else "")
    label = label or path

    def send(sess):
        resp = sess.get(url, headers=JSON_HEADERS, timeout=TIMEOUT)
        body = _classify(resp, label, missing_on_500)
        if expect is not None and not isinstance(body, expect):
            dump_debug("unexpected", resp.text)
            raise HiristUpstreamError(f"unexpected payload on {label}")
        return body
    return _attempts(label, send)


def _feed(path, params, label):
    body = api_get(path, params, label)
    if not isinstance(body.get("data"), list):
        dump_debug("feed", json.dumps(body)[:20000])
        raise HiristUpstreamError(f"unexpected feed payload on {label}")
    return body


# ---- jobs ------------------------------------------------------------------------------------------

def search(params, label="job search"):
    """GET /search with `params` (the backend's own names: query, page,
    size, loc, minexp, maxexp, posting, categoryId) -> {data, page, limit,
    count, totalJobs, count1Year, totalPages, hasMore}."""
    return _feed(SEARCH_PATH, params, label)


def keyword_feed(params, label="skill feed"):
    """GET /keyword/ (keywordId optional: without it, the whole board)."""
    return _feed(KEYWORD_PATH, params, label)


def category_feed(params, label="category feed"):
    return _feed(CATEGORY_PATH, params, label)


def job_detail(job_id):
    """The full job record; HiristNotFound when the id does not exist
    (removed ads still answer, with hasExpired / permanentlyRemoved true)."""
    body = api_get(DETAIL_PATH, {"jobcode": job_id}, label=f"job {job_id}")
    data = body.get("data")
    if not isinstance(data, dict) or data.get("id") is None:
        raise HiristNotFound(f"hirist has no job with the id {job_id}")
    return data


def similar_jobs(job_id, tag_ids):
    body = api_get(SIMILAR_PATH, {"jobcode": job_id, "tags": ",".join(str(t) for t in (tag_ids or []))},
                   label=f"similar jobs of {job_id}")
    return body.get("data") if isinstance(body.get("data"), list) else []


# ---- skills / lookups --------------------------------------------------------------------------------

def tags():
    """[{categoryId, tags: [{id, name, count}]}] — every skill tag with its job count."""
    return api_get(TAGS_PATH, label="skill tags", expect=list)


def tag_info(slug):
    body = api_get(TAG_INFO_PATH, {"slug": slug}, label=f"tag {slug!r}")
    rows = body.get("data") if isinstance(body.get("data"), list) else []
    return rows[0] if rows and isinstance(rows[0], dict) else None


def suggest(query):
    body = api_get(SUGGEST_PATH, {"query": query}, label=f"suggestions {query!r}", expect=list)
    return [s for s in body if isinstance(s, str)]


# ---- companies -------------------------------------------------------------------------------------

def company_list(page, params=None):
    body = api_get(COMPANY_LIST_PATH, {"page": page, **(params or {})}, label=f"company list p{page}")
    if not isinstance(body.get("docs"), list):
        raise HiristUpstreamError(f"unexpected company list payload (page {page})")
    return body


def company_search(keyword, page=0, params=None):
    body = api_get(COMPANY_SEARCH_PATH, {"page": page, "keyword": keyword, **(params or {})},
                   label=f"company search {keyword!r}")
    if not isinstance(body.get("docs"), list):
        raise HiristUpstreamError(f"unexpected company search payload for {keyword!r}")
    return body


def company_data(slug):
    """The AmbitionBox profile behind a company page; {} when the company has none."""
    body = api_get(COMPANY_DATA_PATH, {"slug": slug}, label=f"company {slug!r}")
    data = body.get("data")
    return data if isinstance(data, dict) else {}


def company_jobs(slug, page=0, company_id=None, centralised_id=None):
    """One page (15) of a company's open jobs -> {jobs, hasMore, count}."""
    params = {"page": page, "slug": slug}
    if company_id:
        params["companyId"] = company_id
    else:
        params["cid"] = centralised_id or ""
    body = api_get(COMPANY_JOBS_PATH, params, label=f"jobs of company {slug!r} p{page}")
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    return {"jobs": data.get("jobs") if isinstance(data.get("jobs"), list) else [],
            "hasMore": bool(data.get("hasMore")), "count": body.get("count"), "count1Year": body.get("count1Year")}


def company_slugs():
    body = api_get(COMPANY_SLUGS_PATH, label="company slugs")
    return body.get("data") if isinstance(body.get("data"), list) else []


# ---- recruiters -------------------------------------------------------------------------------------

def recruiter(recruiter_id):
    """The recruiter profile; HiristNotFound for an unknown id (the service
    answers 500 'Internal Server Error' for one)."""
    try:
        body = api_get(RECRUITER_PATH, {"id": recruiter_id}, label=f"recruiter {recruiter_id}", missing_on_500=True)
    except HiristUpstreamError as e:
        if "HTTP 500" in str(e) or "Internal Server Error" in str(e):
            raise HiristNotFound(f"hirist has no recruiter with the id {recruiter_id}")
        raise
    data = body.get("data")
    if not isinstance(data, dict) or not data.get("id"):
        raise HiristNotFound(f"hirist has no recruiter with the id {recruiter_id}")
    return data


def recruiter_jobs(recruiter_id, page=0):
    return _feed(RECRUITER_JOBS_PATH, {"recruiterId": recruiter_id, "page": page},
                 f"jobs of recruiter {recruiter_id} p{page}")


# ---- memo / cache / parallel ---------------------------------------------------------------------------

_memo = OrderedDict()
_memo_lock = threading.Lock()
MEMO_TTL = 600
MEMO_MAX = 64


def memoized(key, fn, ttl=MEMO_TTL):
    now = time.monotonic()
    with _memo_lock:
        hit = _memo.get(key)
        if hit and now - hit[0] < ttl:
            _memo.move_to_end(key)
            return hit[1]
    value = fn()
    with _memo_lock:
        _memo[key] = (now, value)
        _memo.move_to_end(key)
        while len(_memo) > MEMO_MAX:
            _memo.popitem(last=False)
    return value


def shared_raw(name, params, build, ttl):
    """An upstream payload shared by several routes: in-process memo, then
    the service's response cache (pods share it) when one is installed,
    then build(). Without a `cache` module (the standalone package) it is
    the in-process memo alone."""
    try:
        from cache import cached_call
    except ImportError:
        cached_call = None
    seconds = ttl.total_seconds() if hasattr(ttl, "total_seconds") else ttl
    key = (name, json.dumps(params, sort_keys=True))
    if cached_call is None:
        return memoized(key, build, ttl=min(seconds, MEMO_TTL))
    return memoized(key, lambda: cached_call(f"hirist.raw.{name}", params, lambda **_: build(), ttl),
                    ttl=min(seconds, MEMO_TTL))


def run_parallel(fns, workers):
    """Run zero-arg callables in parallel; results align with `fns`. Each
    result is ("ok", value) or ("error", exception)."""
    def guard(fn):
        try:
            return ("ok", fn())
        except Exception as e:
            return ("error", e)
    if not fns:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(fns)))) as ex:
        return list(ex.map(guard, fns))


if __name__ == "__main__":
    # Smoke test: python hirist/fetch.py
    body = search({"query": "python", "page": 0, "size": 5, "loc": "3"})
    print("search:", body.get("totalJobs"), [j.get("title") for j in body["data"][:3]])
    job = job_detail(body["data"][0]["id"])
    print("job:", job.get("title"), job.get("min"), job.get("max"), len(job.get("introText") or ""))
    print("company:", company_data("nagarro-software").get("companyName"))
    print("recruiter:", recruiter(1221).get("name"))
