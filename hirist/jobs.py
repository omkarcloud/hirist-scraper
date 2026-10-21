"""/hirist/jobs/* — job search (the text search and the skill / category /
board feeds behind one endpoint), job details, batch lookup and similar
jobs, from the site's job service."""
from hirist import fetch, lookups, refdata, refs
from hirist import parsers as P


def _workers():
    try:
        import config
        return int(config.HIRIST_WORKERS)
    except Exception:
        return 4


def _filters(query, skill_refs, category, location, min_experience, max_experience, posted_within):
    return {
        "query": query,
        "skills": skill_refs or None,
        "categories": lookups.category_refs(category),
        "locations": lookups.location_refs(location),
        "min_experience": min_experience,
        "max_experience": max_experience,
        "posted_within_days": posted_within,
    }


def search_params(query=None, skill_ids=None, category=None, location=None, min_experience=None,
                  max_experience=None, posted_within=None, page=1, page_size=refdata.PAGE_SIZE):
    """Public params -> (the backend path, its own query). A text query
    goes to /search; otherwise the skill feed (/keyword/) serves every
    combination of skill / category / location / experience / posting age,
    and with none of them the whole board, newest first."""
    common = {
        "page": max(1, page) - 1,
        "size": page_size,
        "loc": ",".join(str(i) for i in location) if location else None,
        "minexp": min_experience,
        "maxexp": max_experience,
        "posting": posted_within,
        "categoryId": ",".join(str(c) for c in category) if category else None,
    }
    if query:
        return "search", {"query": query, **common}
    return "keyword", {"keywordId": ",".join(str(i) for i in skill_ids) if skill_ids else None, **common}


def search(query=None, skill=None, category=None, location=None, min_experience=None, max_experience=None,
           posted_within=None, page=1, page_size=refdata.PAGE_SIZE, include_details=False):
    """One page of jobs. With `query` it is hirist's text search (title,
    skills, company); without, the skill feed filtered by `skill` (tag
    names / ids), `category`, `location`, the experience band and the
    posting age — and with no filter at all, the whole board newest first.
    hirist's text search does not filter by skill tag, so `query` and
    `skill` are mutually exclusive. With include_details every card also
    carries its full record (description, application and recruiter-action
    counts) — one extra call per job, fetched in parallel."""
    if query and skill:
        raise ValueError("Use either `query` (hirist's text search) or `skill` (the tag feed), not both: "
                         "the text search cannot be narrowed by skill tag.")
    skill_ids, skill_refs = lookups.resolve_skill_ids(skill)
    kind, params = search_params(query, skill_ids, category, location, min_experience, max_experience,
                                 posted_within, page, page_size)
    label = f"job search {query!r} p{page}" if query else f"job feed {skill_refs or category or 'all'} p{page}"
    raw = fetch.search(params, label) if kind == "search" else fetch.keyword_feed(params, label)
    result = P.feed_result(raw, page, page_size)
    if include_details and result["jobs"]:
        ids = [card["id"] for card in result["jobs"]]
        outcomes = fetch.run_parallel([lambda i=i: _detail(i) for i in ids], _workers())
        cards = []
        for card, (status, value) in zip(result["jobs"], outcomes):
            if status == "error" and not isinstance(value, fetch.HiristNotFound):
                print(f"hirist: details of job {card['id']} skipped: {value}")
            cards.append(P.merge_card_details(card, value if status == "ok" else None))
        result["jobs"] = cards
    result["filters"] = _filters(query, skill_refs, category, location, min_experience, max_experience,
                                 posted_within)
    return result


# ---- details ------------------------------------------------------------------------------------------------

def _detail(job_id):
    result = P.job_details(fetch.job_detail(job_id))
    if result is None:
        raise fetch.HiristNotFound(f"hirist has no job with the id {job_id}")
    return result


def details(job):
    """The full ad: description (HTML + text), skills with mandatory flags,
    experience band, salary (when disclosed), locations, diversity flags,
    the application / view / recruiter-action counts, the recruiter and the
    company with its AmbitionBox profile. 404 when the site has no such
    job; removed ads still come back with is_active false."""
    return _detail(job)


def batch(jobs):
    """Up to MAX_BATCH jobs by id / link, fetched in parallel. Jobs the site
    does not have are listed under `errors` instead of failing the call."""
    outcomes = fetch.run_parallel([lambda j=j: _detail(j) for j in jobs], _workers())
    out, errors = [], {}
    for job_id, (status, value) in zip(jobs, outcomes):
        if status == "ok":
            out.append(value)
        elif isinstance(value, fetch.HiristNotFound):
            errors[str(job_id)] = "not found"
        else:
            raise value
    return {"jobs": out, "count": len(out), "errors": errors or None}


def similar(job, limit=20):
    """Jobs the site lists as similar to `job` (its skill tags)."""
    record = fetch.job_detail(job)
    tag_ids = [t.get("id") for t in (record.get("tags") or []) if isinstance(t, dict) and t.get("id") is not None]
    rows = fetch.similar_jobs(job, tag_ids)
    jobs = [P.job_card(r) for r in rows if isinstance(r, dict) and r.get("id") != record.get("id")][:limit]
    return {"job": {"id": record.get("id"), "title": P.job_card(record)["title"], "link": P.job_card(record)["link"]},
            "jobs": jobs, "count": len(jobs)}
