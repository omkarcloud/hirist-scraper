"""hirist input parsing: ONE param per input that auto-detects its forms
(tripadvisor QueryOrLinkField convention, never a sibling `url`/`id` pair).
Every resolver returns plain JSON values so validated params stay usable as
a response-cache key, and raises ValueError with a user-facing message.

  job        1679144 | https://www.hirist.tech/j/founding-engineer-backend-1679144
             | founding-engineer-backend-1679144                        -> 1679144
  company    nagarro-software | https://www.hirist.tech/nagarro-software-careers
             | nagarro-software-careers | Nagarro Software (a name, looked up at call time)
                                 -> {"slug": "nagarro-software", "name": None}
                                  | {"slug": None, "name": "Nagarro Software"}
  recruiter  1221 | https://www.hirist.tech/r/1221-prashant-kulkarni | 1221-prashys-gmail-com -> 1221
  location   Bangalore | bengaluru | 3 | remote | Delhi NCR | metros | Pune, Mumbai
                                 -> [3] / [3] / [3] / [132] / [1, 36, 40, …] / [the 15 metro ids] / [5, 2]
             (the picker's names and ids, case-insensitive, alternate
              spellings, umbrella entries expanded to their members)
  category   backend-development | backend-development-jobs | 1 | Backend Development (comma list) -> [1]
  skill      python | 9 | Python, Django (comma list)      -> ["python", "django"] / [9] (names are
             matched against the live tag table at call time, lookups.resolve_skill_ids)
"""
import re
from urllib.parse import unquote, urlparse

from hirist import refdata

_HOST_RE = re.compile(r"(?:^|\.)hirist\.(?:tech|com)$")
_NAME_BAD = re.compile(r"[/?#\\<>\"]")


def _parse_url(value):
    """-> (host, path) when value looks like a hirist URL or host path,
    None when it is plain text. Raises ValueError for another site."""
    raw = (value or "").strip()
    low = raw.lower()
    if low.startswith("//"):
        raw = "https:" + raw
    elif not low.startswith(("http://", "https://")):
        head = low.split("/", 1)[0]
        if not _HOST_RE.search(head):
            return None
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if not _HOST_RE.search(host):
        raise ValueError("Must be a hirist.tech link.")
    return host, unquote(parsed.path)


def _split(value):
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


# ---- jobs -------------------------------------------------------------------------------------------

JOB_HINT = ("Must be a hirist job id (digits, e.g. 1679144) or a job link "
            "(https://www.hirist.tech/j/founding-engineer-backend-development-1679144).")


def resolve_job(value):
    raw = (value or "").strip()
    if raw.isdigit():
        return int(raw)
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(JOB_HINT)
    path = url[1] if url else raw
    if url and not re.search(r"(?:^|/)j/", path):
        raise ValueError(JOB_HINT)
    match = re.search(r"(?:^|/|-)(\d+)/?(?:[?#].*)?$", path)
    if match:
        return int(match.group(1))
    raise ValueError(JOB_HINT)


def resolve_jobs(value, limit=refdata.MAX_BATCH):
    """'1679144, https://www.hirist.tech/j/x-1677571' -> [1679144, 1677571] (deduped, 1..limit)."""
    out = []
    for item in _split(value):
        job_id = resolve_job(item)      # ValueError carries the hint
        if job_id not in out:
            out.append(job_id)
    if not out:
        raise ValueError("Must list at least one job id or link (comma-separated).")
    if len(out) > limit:
        raise ValueError(f"At most {limit} jobs.")
    return out


# ---- companies ----------------------------------------------------------------------------------------

COMPANY_HINT = ("Must be a company page link or slug (https://www.hirist.tech/nagarro-software-careers, "
                "nagarro-software) or a company name.")

_RESERVED_PATHS = {"j", "k", "c", "r", "search", "blog", "company", "jobs", "learning", "sitemap", "contact",
                   "terms", "privacy", "grievances", "it-jobs-in"}


def resolve_company(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(COMPANY_HINT)
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(COMPANY_HINT)
    if url:
        match = re.match(r"^/(?:company/)?([a-z0-9][a-z0-9-]*?)(?:-careers)?/?$", url[1].lower())
        if not match or match.group(1) in _RESERVED_PATHS:
            raise ValueError("Links must be company pages (https://www.hirist.tech/<company>-careers).")
        return {"slug": match.group(1), "name": None}
    match = re.fullmatch(r"([a-z0-9][a-z0-9-]*?)(?:-careers)?/?", raw.lower())
    if match and ("-" in match.group(1) or raw.lower().endswith("-careers")) and " " not in raw:
        return {"slug": match.group(1), "name": None}
    name = " ".join(raw.split())
    if _NAME_BAD.search(name) or len(name) > 150:
        raise ValueError(COMPANY_HINT)
    return {"slug": None, "name": name}


# ---- recruiters ----------------------------------------------------------------------------------------

RECRUITER_HINT = ("Must be a hirist recruiter id (digits, e.g. 1221) or a recruiter profile link "
                  "(https://www.hirist.tech/r/1221-prashant-kulkarni).")


def resolve_recruiter(value):
    raw = (value or "").strip()
    if raw.isdigit():
        return int(raw)
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(RECRUITER_HINT)
    path = url[1] if url else raw
    if url and not re.search(r"(?:^|/)r/", path):
        raise ValueError(RECRUITER_HINT)
    match = re.search(r"(?:^|/)(?:r/)?(\d+)(?:-[^/]*)?/?(?:[?#].*)?$", path)
    if match:
        return int(match.group(1))
    raise ValueError(RECRUITER_HINT)


# ---- locations ----------------------------------------------------------------------------------------------

_LOCATION_ALIASES = {
    "bengaluru": 3, "bengalore": 3, "blr": 3, "bombay": 2, "madras": 6, "calcutta": 5, "gurgaon": 37, "gurugram": 37,
    "ncr": 1, "delhi-ncr": 1, "delhi/ncr": 1, "delhi / ncr": 1, "new delhi": 36, "kochi": 70, "cochin": 70,
    "vizag": 78, "visakhapatnam": 78, "trivandrum": 75, "thiruvananthapuram": 75, "mysuru": 73, "mysore": 73,
    "pondicherry": 85, "puducherry": 85, "vadodara": 56, "baroda": 56, "poona": 7,
    "remote": refdata.REMOTE_ID, "work from home": refdata.REMOTE_ID, "wfh": refdata.REMOTE_ID,
    "anywhere": refdata.ANYWHERE_IN_INDIA_ID, "india": refdata.ANYWHERE_IN_INDIA_ID,
    "anywhere in india": refdata.ANYWHERE_IN_INDIA_ID, "pan india": refdata.ANYWHERE_IN_INDIA_ID,
    "international": refdata.OVERSEAS_ID, "overseas": refdata.OVERSEAS_ID, "abroad": refdata.OVERSEAS_ID,
    "metro": refdata.METROS_ID, "metros": refdata.METROS_ID, "metro cities": refdata.METROS_ID,
}

_INDEX = None


def location_index():
    """lower-cased name / id / alias -> location id (cached)."""
    global _INDEX
    if _INDEX is None:
        index = {}
        for loc_id, name in refdata.LOCATIONS.items():
            index[str(loc_id)] = loc_id
            index[" ".join(name.lower().split())] = loc_id
            # 'Gurgaon/Gurugram', 'Cochin/Kochi', 'Vishakhapatnam/Vizag' -> each half
            for part in re.split(r"\s*/\s*", name.lower()):
                part = " ".join(part.split())
                if part and part not in index:
                    index[part] = loc_id
        for alias, loc_id in _LOCATION_ALIASES.items():
            if loc_id in refdata.LOCATIONS:
                index[alias] = loc_id
        _INDEX = index
    return _INDEX


LOCATION_HINT = ("Must be a city, state, country or region as hirist lists it (Bangalore, Pune, Delhi NCR, "
                 "Gurgaon, Karnataka, Remote, Metros, Anywhere in India, Overseas) or its id; "
                 "see /hirist/locations.")


def resolve_locations(value, limit=10):
    """'Bangalore, bengaluru, remote, metros' -> [3, 132, <the 15 metro ids>]
    (the picker ids the backend accepts, umbrella entries expanded, deduped)."""
    index = location_index()
    out = []
    for item in _split(value):
        key = " ".join(item.lower().split())
        loc_id = index.get(key)
        if loc_id is None:
            raise ValueError(f"'{item}' is not a location hirist knows. " + LOCATION_HINT)
        members = [loc_id] + list(refdata.LOCATION_GROUPS.get(loc_id, []))
        for member in members:
            if member not in out:
                out.append(member)
    if len(_split(value)) > limit:
        raise ValueError(f"At most {limit} locations.")
    return out or None


def location_names(ids):
    return [refdata.LOCATIONS.get(i) for i in (ids or []) if refdata.LOCATIONS.get(i)]


# ---- categories ---------------------------------------------------------------------------------------------

def _category_index():
    index = {}
    for cid, (slug, name) in refdata.CATEGORIES.items():
        index[str(cid)] = cid
        index[slug] = cid
        index[slug[:-len("-jobs")]] = cid
        index[" ".join(name.lower().split())] = cid
        index[re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()] = cid
    index.update({"ai ml": 14, "ai/ml": 14, "aiml": 14, "ml": 14, "ai": 14, "devops": 8, "sre": 8, "qa": 11,
                  "testing": 11, "frontend": 2, "backend": 1, "fullstack": 16, "full-stack": 16, "mobile": 5,
                  "data engineering": 15, "data analytics": 7, "bi": 7, "security": 17, "cyber security": 17,
                  "product": 12, "design": 10, "ui": 10, "ux": 10, "sap": 6, "oracle": 6, "vlsi": 4,
                  "semiconductor": 4, "other": 3})
    return index


CATEGORY_HINT = "see /hirist/categories"


def resolve_categories(value, limit=10):
    """'backend-development, AI/ML, 15' -> [1, 14, 15]."""
    index = _category_index()
    out = []
    for item in _split(value):
        key = " ".join(item.lower().split())
        cid = index.get(key) or index.get(re.sub(r"[^a-z0-9]+", " ", key).strip())
        if cid is None:
            raise ValueError(f"'{item}' is not a job category id, slug or name; {CATEGORY_HINT}.")
        if cid not in out:
            out.append(cid)
    if len(out) > limit:
        raise ValueError(f"At most {limit} categories.")
    return out or None


# ---- skills ------------------------------------------------------------------------------------------------------

def resolve_skills(value, limit=10):
    """'Python, 203, django' -> ['python', 203, 'django']: ids stay ints,
    names are lower-cased and matched against the live tag table at call
    time (lookups.resolve_skill_ids), where an unknown name is a 400."""
    out = []
    for item in _split(value):
        key = item.strip()
        if key.isdigit():
            key = int(key)
        else:
            key = " ".join(key.lower().split())
            if _NAME_BAD.search(key) or len(key) > 80:
                raise ValueError(f"'{item}' is not a skill name or id.")
        if key not in out:
            out.append(key)
    if len(out) > limit:
        raise ValueError(f"At most {limit} skills.")
    return out or None
