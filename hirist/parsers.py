"""Raw hirist payloads -> the API's response shapes. Pure functions over
the job service's JSON (fetch.py); every parser tolerates a partial record.

Dropped on purpose (and why):
  jobs      `refCode` / `refJobId` (promotion tracking codes), `tagIdString`
            (the `tags` list spelled as a string), `createdTime` /
            `createdTimeNoMillis` (the posting date rounded to IST midnight —
            `createdTimeMs` is the exact stamp), `location` (a copy of
            `locations`), `createdByAlias` (the locations joined with '/'),
            `minRatingAb` (a sitewide threshold, 3.8 on every job),
            `applyStatus` / `star` / `brandJobFlag` / `showCompanyLogoFlag` /
            `refreshStatus` / `showRecruiterProfile` / `marker` / `lableId` /
            `jobStatusInfo` / `jobJdContent` / `jobCompanyLogo` /
            `jobCompanyId` / `pendingApply` / `saved` / `applied` /
            `isEvaluationGated` / `isAppActiveWithinLastYear` (presentation
            and per-visitor state, constant or null for an anonymous client),
            `companyStatus` / `status` / `state` (folded into is_active),
            `industry` / `preferedIndustry` / `industryArray` (always empty),
            `categoryIds` (always null), `latitude` / `longitude` / `address`
            (always null), `companyData.companyNameNotAnalyzed` (the name
            again), `companyData.cluster*` / `subCluster*` (the site's
            internal company clustering strings), `recruiter.recruiterActions`
            (masked), `recruiter.logoPath` / `companyLogoFilePath` (the
            company logo again), `ambitionBoxInfo.seo` (page titles for the
            site's own templates), `title` (a page title) and
            `aggregateRatingOneDecimal` (the rating again).
  companies `pageTitle` / `metaKeywords` / `metaDescription` (SEO
            templates with %jobsCount% placeholders), `custId`, `source`,
            `id` (null), `status`, `cluster*`, `showcaseData.templatePath` /
            `templateVersion` / `version` / `quoteLineNo` (the showcase
            renderer's internals), `perks[].logo` (an icon-font code point),
            `ambitionBoxName` / `ambitionBoxId` (inside `ambitionbox`),
            `ambitionBoxData` (a copy of `ambitionBoxInfo`), `redirectionLink`
            (rebuilt as `link`).
  recruiter `uuid` (the id and email base64-encoded), `recruiterTags[].
            tagNameLower`, `logoLink` (empty).
"""
from math import ceil

from hirist import refdata
from hirist import shared as S
from hirist.shared import as_dict, as_list, g


# ---- taxonomy entries --------------------------------------------------------------------------------------

def category_ref(category_id):
    cid = S.to_int(category_id)
    if not cid:
        return None
    slug, name = refdata.CATEGORIES.get(cid, (None, None))
    return {"id": cid, "slug": slug, "name": name, "link": S.category_link(slug)}


def functional_area_ref(value):
    fid = S.to_int(value)
    if not fid:
        return None
    return {"id": fid, "name": refdata.FUNCTIONAL_AREAS.get(fid)}


def skill_ref(raw):
    raw = as_dict(raw)
    name = S.text(raw.get("name") or raw.get("tagName"))
    if not name and raw.get("id") is None:
        return None
    return {"id": S.to_int(raw.get("id") or raw.get("tagId")), "name": name,
            "is_mandatory": S.flag(raw.get("isMandatory")) if "isMandatory" in raw else None,
            "link": S.skill_link(name)}


def location_ref(raw):
    raw = as_dict(raw)
    name = S.text(raw.get("name"))
    if not name:
        return None
    loc_id = S.to_int(raw.get("id"))
    return {"id": loc_id, "name": name, "is_remote": name.lower() in refdata.REMOTE_NAMES}


def _locations(raw):
    out = []
    for row in as_list(raw.get("locations") or raw.get("location")):
        entry = location_ref(row)
        if entry and entry["name"] not in [e["name"] for e in out]:
            out.append(entry)
    return out


# ---- AmbitionBox company profile ------------------------------------------------------------------------

def _benefit(raw):
    raw = as_dict(raw)
    return {"name": S.text(raw.get("name")), "icon": S.link(raw.get("iconUrl")),
            "reported_by": S.count(raw.get("count")), "respondents": S.count(raw.get("totalCount"))}


def _job_profile(raw):
    raw = as_dict(raw)
    return {"name": S.text(raw.get("name")), "rating": S.rating(raw.get("rating")),
            "reviews_count": S.count(raw.get("count")), "link": S.link(raw.get("url"))}


JOB_ROW_PROFILES = 10      # AmbitionBox role ratings kept on a job's company block


def ambitionbox_profile(raw, max_profiles=None):
    """The AmbitionBox block the site attaches to companies (job cards,
    company pages): identity, about, size, rating, benefits, job profiles.
    `max_profiles` keeps only the most-reviewed roles (a big employer has
    260+ of them, ~40 KB, repeated on every one of its job rows);
    `top_job_profiles_count` always carries the full count."""
    raw = as_dict(raw)
    if not raw or not (raw.get("ambitionBoxCompanyId") or raw.get("companyName")):
        return None
    benefits = raw.get("benefits")
    if isinstance(benefits, dict):      # the company page nests the list under its own counts
        benefit_rows, benefits_link = benefits.get("benefits"), benefits.get("benefitsUrl")
        total_benefits, reported = benefits.get("totalBenefits"), benefits.get("usersReportedBenefits")
    else:
        benefit_rows, benefits_link = benefits, raw.get("benefitsUrl")
        total_benefits, reported = raw.get("totalBenefits"), raw.get("usersReportedBenefits")
    profiles = raw.get("topJobProfilesEntities")
    if not isinstance(profiles, list):
        profiles = g(raw, "topJobProfiles", "entities")
    roles = [_job_profile(p) for p in as_list(profiles) if isinstance(p, dict)]
    roles_count = len(roles)
    if max_profiles is not None:
        roles = sorted(roles, key=lambda r: -(r["reviews_count"] or 0))[:max_profiles]
    offices = []
    for row in as_list(raw.get("officeLocations")):
        city = S.text(row.get("cityName") if isinstance(row, dict) else row)
        if city and city not in offices:
            offices.append(city)
    return {
        "id": S.to_int(raw.get("ambitionBoxCompanyId")),
        "name": S.text(raw.get("companyName")),
        "logo": S.link(raw.get("companyLogo")),
        "about": S.html_to_text(raw.get("aboutCompany")),
        "founded_year": S.year(raw.get("foundedYear")),
        "company_type": S.text(raw.get("companyType")),
        "primary_industry": S.text(raw.get("primaryIndustry")),
        "nature_of_business": S.text_list(raw.get("natureOfBusiness")),
        "tags": S.text_list(raw.get("otherTags")),
        "headquarters": S.text(raw.get("hq")),
        "office_locations": offices,
        "employees": S.text(raw.get("totalEmployees")),
        "employees_india": S.text(raw.get("totalEmployeesIndia")),
        "rating": S.rating(raw.get("aggregateRating")),
        "reviews_count": S.count(raw.get("reviewsCount")),
        "reviews_link": S.link(raw.get("url")),
        "benefits": {
            "count": S.count(total_benefits),
            "reported_by": S.count(reported),
            "link": S.link(benefits_link),
            "items": [_benefit(b) for b in as_list(benefit_rows) if isinstance(b, dict)],
        },
        "top_job_profiles": roles,
        "top_job_profiles_count": roles_count,
        "top_job_profiles_link": S.link(raw.get("topJobProfilesUrl")),
    }


# ---- companies on job cards -------------------------------------------------------------------------------

def _company_logo(raw):
    """The company's logo as the site shows it: the per-job upload, else the
    AmbitionBox one; empty strings and the site's placeholder host -> None."""
    for key in ("logo", "logoPath", "companyLogoFilePath"):
        value = S.link(raw.get(key))
        if value:
            return value
    return S.link(g(raw, "ambitionBoxInfo", "companyLogo"))


def job_company(raw, job=None):
    """The `companyData` block of a job (+ the job-level company fields)."""
    raw = as_dict(raw)
    job = as_dict(job)
    name = S.text(raw.get("companyName"))
    careers_slug = S.text(job.get("careerCompanyName"))
    if not name and not careers_slug and not job.get("creatorDomainName"):
        return None
    return {
        "id": S.to_int(raw.get("companyId")) or None,
        "name": name,
        "logo": _company_logo(raw),
        "domain": S.text(job.get("creatorDomainName") or job.get("companyDomain")),
        "careers_slug": careers_slug,
        "careers_link": S.company_link(careers_slug),
        "is_verified": S.to_int(raw.get("companyStatus")) == 1 if raw.get("companyStatus") is not None else None,
        "ambitionbox": ambitionbox_profile(raw.get("ambitionBoxInfo"), max_profiles=JOB_ROW_PROFILES),
    }


def without_company_profile(job):
    """A job row under its own company's page: the parent already carries
    the AmbitionBox profile, so the row's copy is dropped (set to null)."""
    if isinstance(job, dict) and isinstance(job.get("company"), dict):
        job = {**job, "company": {**job["company"], "ambitionbox": None}}
    return job


def job_recruiter(raw):
    raw = as_dict(raw)
    rid = S.to_int(raw.get("recruiterId"))
    name = S.text(raw.get("recruiterName"))
    if not rid and not name:
        return None
    return {
        "id": rid,
        "name": name,                    # '*****' (masked for anonymous callers on /detail) -> None
        "designation": S.text(raw.get("designation")),
        "photo": S.link(raw.get("profilePicUrl")),
        "company_id": S.to_int(raw.get("recruiterCompanyId")) or None,
        "link": S.recruiter_link(rid, name),
    }


def showcase_ref(raw):
    raw = as_dict(raw)
    if not raw:
        return None
    return {"id": S.to_int(raw.get("showcaseCompanyId") or raw.get("centralisedCompanyID")),
            "name": S.text(raw.get("showcaseName")), "link": S.link(raw.get("showcaseUrl"))}


# ---- job cards ---------------------------------------------------------------------------------------------

def _diversity(raw):
    return {
        "prefers_women": S.flag(raw.get("femaleCandidate")),
        "welcomes_women_returning_to_work": S.flag(raw.get("femaleBackWorkForce")),
        "is_open_to_differently_abled": S.flag(raw.get("differentlyAbled")),
        "is_open_to_ex_defence": S.flag(raw.get("exDefence")),
    }


def _graduation_batch(raw):
    lo, hi = S.year(raw.get("minBatch")), S.year(raw.get("maxBatch"))
    if lo is None and hi is None:
        return None
    return {"min_year": lo, "max_year": hi}


def _posted(raw):
    stamp = S.iso_datetime_ms(raw.get("createdTimeMs")) or S.iso_datetime_ms(raw.get("createdTime"))
    return stamp


def job_card(raw):
    """A feed card (search / skill / category / company / recruiter feeds)."""
    raw = as_dict(raw)
    job_id = S.to_int(raw.get("id"))
    title = S.text(raw.get("title"))
    locations = _locations(raw)
    posted_at = _posted(raw)
    return {
        "id": job_id,
        "title": title,
        "designation": S.text(raw.get("jobdesignation")),
        "link": S.link(raw.get("jobDetailUrl"))
        if S.is_site_link(raw.get("jobDetailUrl")) and S.job_id_from_link(raw.get("jobDetailUrl")) == job_id
        else S.job_link(job_id, title),
        "category": category_ref(raw.get("categoryId")),
        "functional_area": functional_area_ref(raw.get("functionalArea")),
        "experience": {"min_years": S.to_int(raw.get("min")), "max_years": S.to_int(raw.get("max"))},
        "salary": S.salary(raw.get("minSal"), raw.get("maxSal"), raw.get("hideSal")),
        "skills": [s for s in (skill_ref(t) for t in as_list(raw.get("tags"))) if s],
        "locations": locations,
        "other_locations": S.split_list(raw.get("otherLocation")),
        "is_remote": any(l["is_remote"] for l in locations) or bool(S.flag(raw.get("workFromHome"))),
        "is_work_from_home": S.flag(raw.get("workFromHome")),
        "is_premium": S.flag(raw.get("premium")),
        "is_branded": S.flag(raw.get("brandedJd")),
        "is_confidential": S.flag(raw.get("confidential")),
        "has_assessment": bool(S.to_int(raw.get("assessmentFlags"))),
        "requires_video_resume": S.flag(raw.get("mediaResume")),
        "video_link": S.link(raw.get("videoUrl")),
        "apply_link": S.link(raw.get("applyUrl")),
        "graduation_batch": _graduation_batch(raw),
        "diversity": _diversity(raw),
        "stats": {"applications": S.count(raw.get("applyCount")), "views": S.count(raw.get("hits"))},
        "posted_at": posted_at,
        "posted_date": posted_at[:10] if posted_at else None,
        "company": job_company(raw.get("companyData"), raw),
        "recruiter": job_recruiter(raw.get("recruiter")),
        "showcase": showcase_ref(raw.get("showcase")),
    }


def feed_result(raw, page, page_size):
    """A feed page -> {jobs, pagination}. `page` is this API's 1-based page."""
    raw = as_dict(raw)
    total = S.count(raw.get("totalJobs"))
    size = S.to_int(raw.get("limit")) or page_size
    pages = S.to_int(raw.get("totalPages"))
    if pages is None and total is not None:
        pages = ceil(total / size) if size else 0
    jobs = [job_card(c) for c in as_list(raw.get("data")) if isinstance(c, dict)]
    if pages is None:   # feeds without totals (similar, company) -> extend while hasMore
        pages = page + 1 if raw.get("hasMore") else page
    pages = min(pages, refdata.MAX_PAGE)     # the deepest `page` the routes accept
    return {
        "jobs": jobs,
        "jobs_last_year": S.count(raw.get("count1Year")),
        "pagination": {"page": page, "items_per_page": size, "total_pages": max(pages, page if jobs else 0),
                       "total_count": total},
    }


# ---- job details ------------------------------------------------------------------------------------------

def job_details(raw):
    """The /detail record: the card plus the description, the counts the
    detail page shows, the activity state and the recruiter's company."""
    raw = as_dict(raw)
    if raw.get("id") is None:
        return None
    card = job_card(raw)
    description = S.html_fragment(raw.get("introText"))
    expired = S.flag(raw.get("hasExpired"))
    removed = S.flag(raw.get("permanentlyRemoved"))
    active = S.flag(raw.get("active"))
    is_active = (active if active is not None else True) and not expired and not removed
    posted_from_ats = S.flag(raw.get("ats"))
    card.update({
        "description_html": description,
        "description_text": S.html_to_text(description),
        "stats": {
            "applications": S.count(raw.get("applicationCount")) if S.count(raw.get("applicationCount")) is not None
            else card["stats"]["applications"],
            "views": card["stats"]["views"],
            "recruiter_actions": S.count(raw.get("recruiterActionCount")),
            "openings": S.count(raw.get("jobCount")),
        },
        "is_active": is_active,
        "has_expired": bool(expired),
        "is_removed": bool(removed),
        "is_posted_via_ats": posted_from_ats,
        "is_crawled": S.flag(raw.get("crawled")),
        "branded_description_link": S.link(raw.get("brandedS3")),
    })
    return card


def merge_card_details(card, details):
    """A search card + its /detail record (include_details): the detail's
    richer fields win, the card's counts survive the masking."""
    if not details:
        return card
    out = dict(details)
    for key in ("applications", "views"):
        if out["stats"].get(key) is None and card["stats"].get(key) is not None:
            out["stats"][key] = card["stats"][key]
    if out.get("recruiter") and card.get("recruiter") and not out["recruiter"].get("name"):
        out["recruiter"]["name"] = card["recruiter"].get("name")
        out["recruiter"]["link"] = card["recruiter"].get("link")
    return out


# ---- companies -----------------------------------------------------------------------------------------------

def _showcase(raw):
    raw = as_dict(raw)
    if not raw or not (raw.get("companyId") or raw.get("showcaseLink")):
        return None
    return {
        "company_id": S.to_int(raw.get("companyId")),
        "name": S.text(raw.get("companyName")),
        "link": S.link(raw.get("showcaseLink")),
        "description": S.text(raw.get("description")),
        "domain": S.text(raw.get("domain")),
        "images": [S.link(i) for i in as_list(raw.get("images")) if S.link(i)],
        "perks": S.text_list([as_dict(p).get("title") for p in as_list(raw.get("perks"))]),
        "jobs_count": S.count(raw.get("jobCount")),
        "industries": S.text_list([as_dict(c).get("name") for c in as_list(raw.get("category"))]),
        "skills": S.text_list([as_dict(t).get("name") for t in as_list(raw.get("tag"))]),
        "locations": S.text_list([as_dict(l).get("name") for l in as_list(raw.get("location"))]),
    }


def company_card(raw):
    """A company directory record (/company-list, /company-list/search)."""
    raw = as_dict(raw)
    slug = S.text(raw.get("slug"))
    showcase = raw.get("showcaseData")
    if not isinstance(showcase, dict) and raw.get("showcaseLink"):
        # the search index flattens the showcase block onto the record
        showcase = {k: raw.get(k) for k in ("companyId", "companyName", "description", "showcaseLink", "images",
                                             "perks", "jobCount", "category", "tag", "location", "domain")}
    names = S.text_list(raw.get("companyNames") if isinstance(raw.get("companyNames"), list)
                        else [raw.get("companyNames")])
    ambitionbox = ambitionbox_profile(raw.get("ambitionBoxInfo") or raw.get("ambitionBoxData"))
    return {
        "slug": slug,
        "name": S.text(raw.get("companyName")) or (names[0] if names else None),
        "link": S.company_link(slug),
        "id": S.to_int(raw.get("companyId") or raw.get("companyIds")) or None,
        "centralised_id": S.to_int(raw.get("centralisedCompanyId")) or None,
        "logo": ambitionbox["logo"] if ambitionbox else None,
        "domains": S.split_list(raw.get("companyDomains")),
        "other_names": [n for n in names if n != S.text(raw.get("companyName"))],
        "description": S.text(raw.get("description")),
        "jobs_count": S.count(raw.get("jobCount")),
        "locations": S.text_list([as_dict(l).get("name") for l in as_list(raw.get("location"))]),
        "rating": ambitionbox["rating"] if ambitionbox else None,
        "reviews_count": ambitionbox["reviews_count"] if ambitionbox else None,
        "has_showcase": bool(S.flag(raw.get("hasShowcaseData"))) or bool(_showcase(showcase)),
        "showcase": _showcase(showcase),
        "ambitionbox": ambitionbox,
        "created_at": S.iso_datetime(raw.get("createdAt")),
        "updated_at": S.iso_datetime(raw.get("updatedAt")),
    }


def company_list_result(raw, page, page_size):
    raw = as_dict(raw)
    companies = [company_card(d) for d in as_list(raw.get("docs")) if isinstance(d, dict)]
    has_more = raw.get("hasMore")
    total = S.count(raw.get("numFound"))
    if has_more is None:      # the keyword search: one page, numFound is the total
        pages = 1 if companies else 0
    else:                     # the directory: numFound is the page's own count
        total = None
        pages = min(page + 1, refdata.MAX_PAGE) if has_more else page
    return {"companies": companies,
            "pagination": {"page": page, "items_per_page": page_size, "total_pages": pages, "total_count": total}}


def company_profile(doc, data, slug):
    """A company page: the directory record + the AmbitionBox profile."""
    card = company_card(doc) if doc else {"slug": slug, "name": None, "link": S.company_link(slug), "id": None,
                                          "centralised_id": None, "logo": None, "domains": [], "other_names": [],
                                          "description": None, "jobs_count": None, "locations": [], "rating": None,
                                          "reviews_count": None, "has_showcase": False, "showcase": None,
                                          "ambitionbox": None, "created_at": None, "updated_at": None}
    data = as_dict(data)
    profile = ambitionbox_profile(data) or card.get("ambitionbox")
    if profile:
        card["ambitionbox"] = profile
        card["logo"] = card["logo"] or profile["logo"]
        card["rating"] = card["rating"] or profile["rating"]
        card["reviews_count"] = card["reviews_count"] or profile["reviews_count"]
        card["name"] = card["name"] or profile["name"]
    card["centralised_id"] = card["centralised_id"] or S.to_int(data.get("centralisedCompanyId")) or None
    card["id"] = card["id"] or S.to_int(data.get("companyIds")) or None
    return card


def company_jobs_result(raw, page):
    raw = as_dict(raw)
    if isinstance(raw.get("data"), dict):      # the backend's own envelope (fetch.company_jobs flattens it)
        raw = {**raw, **raw["data"]}
    total = S.count(raw.get("count"))
    size = refdata.COMPANY_JOBS_PAGE_SIZE
    jobs = [job_details(j) or job_card(j) for j in as_list(raw.get("jobs")) if isinstance(j, dict)]
    pages = ceil(total / size) if total else (page if jobs else 0)
    return {"jobs": jobs, "jobs_last_year": S.count(raw.get("count1Year")),
            "pagination": {"page": page, "items_per_page": size, "total_pages": pages, "total_count": total}}


# ---- recruiters ---------------------------------------------------------------------------------------------

def recruiter_profile(raw):
    raw = as_dict(raw)
    rid = S.to_int(raw.get("id"))
    if not rid:
        return None
    name = S.text(raw.get("name"))
    skills = []
    for row in as_list(raw.get("recruiterTags")):
        row = as_dict(row)
        skill = S.text(row.get("tagName"))
        if skill:
            skills.append({"id": S.to_int(row.get("tagId")), "name": skill, "jobs_count": S.count(row.get("count")),
                           "link": S.skill_link(skill)})
    return {
        "id": rid,
        "name": name,
        "link": S.link(raw.get("profileUrl")) or S.recruiter_link(rid, name),
        "photo": S.link(raw.get("image")),
        "organisation": S.text(raw.get("organisation")),
        "designation": S.text(raw.get("designation")),
        "location": S.text(raw.get("location")),
        "about": S.text(raw.get("about")),
        "website": S.website(raw.get("website")),
        "social": {"linkedin": S.website(raw.get("linkedInUrl")), "facebook": S.website(raw.get("facebookUrl")),
                   "twitter": S.website(raw.get("twitterUrl"))},
        "last_login_date": S.iso_date(raw.get("lastLogin")),
        "last_active_date": S.iso_date(raw.get("lastActive")),
        "last_job_posted_date": S.iso_date(raw.get("lastJobPostedDate")),
        "hiring_for": skills,
    }


# ---- skills -----------------------------------------------------------------------------------------------

def skill_table(raw):
    """/tags -> [{category: {...}, skills: [{id, name, jobs_count, link}]}]."""
    out = []
    for block in as_list(raw):
        block = as_dict(block)
        category = category_ref(block.get("categoryId"))
        skills = []
        for row in as_list(block.get("tags")):
            row = as_dict(row)
            name = S.text(row.get("name"))
            if not name:
                continue
            skills.append({"id": S.to_int(row.get("id")), "name": name, "jobs_count": S.count(row.get("count")),
                           "link": S.skill_link(name)})
        if category or skills:
            out.append({"category": category, "skills": skills})
    return out


def tag_info(raw):
    raw = as_dict(raw)
    name = S.text(raw.get("tagName"))
    if not name:
        return None
    return {"id": S.to_int(raw.get("id")), "name": name, "slug": S.text(raw.get("tagSlug")),
            "link": S.skill_link(name), "description": S.text(raw.get("description")),
            "jobs_count_all_time": S.count(raw.get("tagCount"))}
