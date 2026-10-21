"""/hirist/companies/* — the company directory (browse by location /
category, or search by name), a company's page (its directory record +
AmbitionBox profile + showcase) and its open jobs.

A `company` param arrives resolved by refs.resolve_company: a page slug
(or /<slug>-careers link), or a name that is matched against the site's
own company search (exact name first, else the first hit)."""
import re

from hirist import cache_config as ttl
from hirist import fetch, refdata
from hirist import parsers as P
from hirist import shared as S
from hirist.shared import as_dict


def _list_params(location, category):
    # the site's company directory takes `loc` (ids) and `catId` — which its
    # own bundle sends as the category id minus one (0 = every category)
    return {
        "loc": ",".join(str(i) for i in location) if location else None,
        "catId": ",".join(str(c - 1) for c in category if c - 1 > 0) if category else None,
    }


def search(query=None, location=None, category=None, page=1):
    """One page of the company directory (50 a page, newest first) or, with
    `query`, the companies whose name matches it (one page). `location` and
    `category` narrow the directory."""
    params = _list_params(location, category)
    if query:
        raw = fetch.company_search(query, page - 1, params)
        # the search index lower-cases names: restore each page's own name
        try:
            raw = {**raw, "docs": [_with_proper_name(d, S.text(d.get("slug"))) if isinstance(d, dict) else d
                                   for d in raw.get("docs") or []]}
        except fetch.HiristUpstreamError as e:
            print(f"hirist: proper company names skipped: {e}")
    else:
        raw = fetch.company_list(page - 1, params)
    result = P.company_list_result(raw, page, refdata.COMPANY_LIST_PAGE_SIZE)
    result["filters"] = {"query": query, "locations": [{"id": i, "name": refdata.LOCATIONS.get(i)} for i in (location or [])] or None,
                         "categories": [P.category_ref(c) for c in (category or [])] or None}
    return result


# ---- resolving --------------------------------------------------------------------------------------------

def _slug_table():
    """{slug: proper-cased name} from /companies/slugs ('Infotel Jobs' ->
    'Infotel'), cached a week — the search index lower-cases every name
    and misses some pages, this table has them all."""
    def build():
        table = {}
        for entry in fetch.company_slugs():
            slug, name = S.text(as_dict(entry).get("slug")), S.text(as_dict(entry).get("name")) or ""
            if slug:
                table[slug] = name[:-5].strip() if name.lower().endswith(" jobs") else name
        return table
    return fetch.shared_raw("company_slugs", {}, build, ttl.COMPANY_SLUGS_RAW_CACHE)


def _search_docs(keyword):
    return [r for r in fetch.company_search(keyword, 0).get("docs") or [] if isinstance(r, dict) and S.text(r.get("slug"))]


def _with_proper_name(doc, slug):
    """The search index lower-cases company names; restore the page's own."""
    doc = dict(doc)
    name = S.text(doc.get("companyName")) or ""
    proper = _slug_table().get(slug)
    if proper and (not name or name == name.lower()):
        doc["companyName"] = proper
    return doc


def _doc_by_slug(slug):
    """The directory record of a page slug: the site's company search on the
    slug's words (its index covers names and slugs), matched on the slug;
    a page the index misses gets a minimal record from the slug table."""
    for row in _search_docs(" ".join(slug.split("-"))):
        if S.text(row.get("slug")) == slug:
            return _with_proper_name(row, slug)
    proper = _slug_table().get(slug)
    if proper is not None:
        for row in _search_docs(proper):
            if S.text(row.get("slug")) == slug:
                return _with_proper_name(row, slug)
        return {"slug": slug, "companyName": proper}
    return None


def _doc_by_name(name):
    """A company name -> its directory record: an exact name in the search
    index, else an exact name in the slug table, else the index's first hit."""
    key = name.lower()
    rows = _search_docs(name)
    for row in rows:
        names = [S.text(row.get("companyName")) or ""]
        extra = row.get("companyNames")
        names += S.text_list(extra if isinstance(extra, list) else [extra])
        if key in [n.lower() for n in names]:
            return _with_proper_name(row, S.text(row.get("slug")))
    for slug, proper in _slug_table().items():
        if proper.lower() == key:
            return _doc_by_slug(slug) or {"slug": slug, "companyName": proper}
    # the index matches ANY word ('zzqqxx corp' -> every 'corp'): accept the
    # first hit only when it carries every word of the name
    words = [w for w in re.split(r"[^a-z0-9]+", key) if w]
    for row in rows:
        haystack = " ".join([S.text(row.get("companyName")) or "", S.text(row.get("slug")) or ""]).lower()
        if words and all(w in haystack for w in words):
            return _with_proper_name(row, S.text(row.get("slug")))
    raise fetch.HiristNotFound(f"hirist has no company named {name!r}")


def resolve_doc(company):
    """A resolved `company` ref -> (slug, directory record or None); cached."""
    if company.get("slug"):
        slug = company["slug"]
        doc = fetch.shared_raw("company_doc_by_slug", {"slug": slug}, lambda: _doc_by_slug(slug), ttl.COMPANY_DOC_CACHE)
        return slug, doc
    name = company["name"]
    doc = fetch.shared_raw("company_doc_by_name", {"name": name.lower()}, lambda: _doc_by_name(name), ttl.COMPANY_DOC_CACHE)
    return S.text(doc.get("slug")), doc


# ---- profiles ----------------------------------------------------------------------------------------------

def details(company, include_jobs=True):
    """The company page: identity, domains, description, locations, job
    count, the showcase (perks, photos, skills, industries) and the
    AmbitionBox profile (about, size, rating, reviews, benefits, top job
    profiles); with include_jobs the first page of its open jobs."""
    slug, doc = resolve_doc(company)
    data = fetch.company_data(slug)
    if not doc and not data:
        raise fetch.HiristNotFound(f"hirist has no company page for {slug!r}")
    out = P.company_profile(doc, data, slug)
    if include_jobs:
        try:
            jobs = _jobs_page(slug, out, 1)
            out["jobs"] = jobs["jobs"]
            out["jobs_count"] = jobs["pagination"]["total_count"] if jobs["pagination"]["total_count"] is not None else out["jobs_count"]
        except fetch.HiristUpstreamError as e:
            print(f"hirist: jobs of company {slug!r} skipped: {e}")
            out["jobs"] = None
    else:
        out["jobs"] = None
    return out


def _jobs_page(slug, head, page):
    """One page of the company's jobs; each row's copy of the company's
    AmbitionBox profile is dropped, the response carries it once."""
    raw = fetch.company_jobs(slug, page - 1, company_id=head.get("id"), centralised_id=head.get("centralised_id"))
    result = P.company_jobs_result(raw, page)
    result["jobs"] = [P.without_company_profile(j) for j in result["jobs"]]
    return result


def open_jobs(company, page=1):
    """One page (15) of a company's open jobs — the full records, as the
    company page lists them."""
    slug, doc = resolve_doc(company)
    data = fetch.company_data(slug)
    if not doc and not data:
        raise fetch.HiristNotFound(f"hirist has no company page for {slug!r}")
    head = P.company_profile(doc, data, slug)
    result = _jobs_page(slug, head, page)
    result["company"] = {"slug": head["slug"], "name": head["name"], "link": head["link"], "id": head["id"],
                         "logo": head["logo"], "jobs_count": result["pagination"]["total_count"],
                         "rating": head["rating"], "reviews_count": head["reviews_count"],
                         "ambitionbox": head["ambitionbox"]}
    return result
