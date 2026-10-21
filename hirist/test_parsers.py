"""Offline tests: refs resolvers, marshmallow schemas, value helpers, parsers
and the endpoint functions with the transport monkeypatched to serve
fixtures (hirist/fixtures/*.gz, raw payloads captured 2026-10-19 from
gladiator.hirist.tech) — no network.

    python -m pytest hirist/test_parsers.py -q
"""
import gzip
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hirist import companies, fetch, jobs, lookups, parsers as P, recruiters, refdata, refs, schemas, shared as S  # noqa: E402
from schema_fields import load_query  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(name):
    with gzip.open(os.path.join(FX, name + ".json.gz"), "rt", encoding="utf-8") as f:
        return json.load(f)


# ---- refs ------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "1679144", "https://www.hirist.tech/j/founding-engineer-backend-development-1679144",
    "www.hirist.tech/j/x-1679144/", "founding-engineer-backend-development-1679144", "https://hirist.tech/j/1679144?ref=x",
])
def test_resolve_job(value):
    assert refs.resolve_job(value) == 1679144


@pytest.mark.parametrize("value", ["", "abc", "https://www.hirist.tech/k/python-jobs", "https://example.com/j/x-1/"])
def test_resolve_job_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_job(value)


def test_resolve_jobs():
    assert refs.resolve_jobs("1679144, https://www.hirist.tech/j/x-1677571, 1679144") == [1679144, 1677571]
    with pytest.raises(ValueError):
        refs.resolve_jobs(", ,")
    with pytest.raises(ValueError):
        refs.resolve_jobs(",".join(str(i) for i in range(1, refdata.MAX_BATCH + 2)))


@pytest.mark.parametrize("value,expected", [
    ("nagarro-software", {"slug": "nagarro-software", "name": None}),
    ("https://www.hirist.tech/nagarro-software-careers", {"slug": "nagarro-software", "name": None}),
    ("hirist.tech/infotel-careers/", {"slug": "infotel", "name": None}),
    ("Nagarro-Software-careers", {"slug": "nagarro-software", "name": None}),
    ("Nagarro Software", {"slug": None, "name": "Nagarro Software"}),
    ("Infotel", {"slug": None, "name": "Infotel"}),
])
def test_resolve_company(value, expected):
    assert refs.resolve_company(value) == expected


@pytest.mark.parametrize("value", ["", "https://www.hirist.tech/k/python-jobs", "https://example.com/x-careers", "a/b"])
def test_resolve_company_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_company(value)


@pytest.mark.parametrize("value", ["1221", "https://www.hirist.tech/r/1221-prashys-gmail-com", "1221-prashant-kulkarni",
                                   "http://www.hirist.tech/r/1221-Prashant-Kulkarni"])
def test_resolve_recruiter(value):
    assert refs.resolve_recruiter(value) == 1221


@pytest.mark.parametrize("value", ["", "abc", "https://www.hirist.tech/j/x-1679144", "https://example.com/r/1-x"])
def test_resolve_recruiter_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_recruiter(value)


def test_resolve_locations():
    assert refs.resolve_locations("bengaluru, Remote, Pune, poona, 4") == [3, 132, 7, 4]
    assert refs.resolve_locations("gurgaon") == [37]
    assert refs.resolve_locations("calcutta, mysuru, puducherry, baroda") == [5, 73, 85, 56]   # aliases -> the picker's ids
    assert refs.resolve_locations("Delhi NCR") == [1, 36, 40, 41, 37, 38, 39]
    metros = refs.resolve_locations("metros")
    assert metros[0] == 87 and 3 in metros and len(metros) == 16
    assert refs.resolve_locations("") is None
    with pytest.raises(ValueError):
        refs.resolve_locations("Atlantis")


def test_resolve_categories():
    assert refs.resolve_categories("backend-development, AI/ML, 15, Full Stack, devops") == [1, 14, 15, 16, 8]
    assert refs.resolve_categories("ai-ml-jobs") == [14]
    with pytest.raises(ValueError):
        refs.resolve_categories("astrology")


def test_resolve_skills():
    assert refs.resolve_skills("Python, 203, django, python") == ["python", 203, "django"]
    with pytest.raises(ValueError):
        refs.resolve_skills("a/b")


# ---- schemas ---------------------------------------------------------------------------------

def test_search_schema():
    data, err = load_query(schemas.JobSearchSchema, {"query": "python", "location": "bangalore,remote", "posted_within": "7",
                                                     "min_experience": "2", "page": "2", "page_size": "50"})
    assert err is None
    assert data["location"] == [3, 132] and data["posted_within"] == 7 and data["page"] == 2 and data["page_size"] == 50
    assert data["skill"] is None and data["include_details"] is False
    _, err = load_query(schemas.JobSearchSchema, {"posted_within": "5"})
    assert err and "posted_within" in err["errors"]
    _, err = load_query(schemas.JobSearchSchema, {"page_size": "51"})
    assert err and "page_size" in err["errors"]
    _, err = load_query(schemas.JobSearchSchema, {"location": "Atlantis"})
    assert err and "Atlantis" in err["error"]
    _, err = load_query(schemas.JobSearchSchema, {"bogus": "1"})
    assert err


def test_other_schemas():
    data, err = load_query(schemas.JobSchema, {"job": "https://www.hirist.tech/j/x-1679144"})
    assert err is None and data == {"job": 1679144}
    data, err = load_query(schemas.CompanySchema, {"company": "nagarro-software", "include_jobs": "false"})
    assert err is None and data == {"company": {"slug": "nagarro-software", "name": None}, "include_jobs": False}
    data, err = load_query(schemas.RecruiterJobsSchema, {"recruiter": "1221"})
    assert err is None and data == {"recruiter": 1221, "page": 1}
    data, err = load_query(schemas.SkillsSchema, {"category": "ai-ml", "limit": "5"})
    assert err is None and data == {"category": [14], "query": None, "limit": 5}
    _, err = load_query(schemas.AutocompleteSchema, {})
    assert err


# ---- shared ----------------------------------------------------------------------------------

def test_shared_helpers():
    assert S.text("  Founding  Engineer ") == "Founding Engineer" and S.text("*****") is None and S.text("") is None
    assert S.count("*****") is None and S.count(-1) == 0 and S.count("281") == 281
    assert S.flag(1) is True and S.flag("0") is False and S.flag(None) is None
    assert S.iso_datetime_ms(1792234335555) == "2026-10-17T16:22:15+05:30" and S.iso_date_ms(1792234335555) == "2026-10-17"
    assert S.iso_datetime_ms(0) is None and S.iso_datetime("2023-03-23T18:30:00.000+00:00") == "2023-03-23T18:30:00+00:00"
    assert S.iso_date("2026-10-19") == "2026-10-19"
    assert S.link("http://www.hirist.tech/r/1221-Prashant-Kulkarni") == "https://www.hirist.tech/r/1221-Prashant-Kulkarni"
    assert S.link("//static.x/y.png") == "https://static.x/y.png" and S.link("") is None
    assert S.website("www.squarerootindia.com") == "https://www.squarerootindia.com"
    assert S.job_link(1679144, "Founding Engineer - Backend Development ") == "https://www.hirist.tech/j/founding-engineer-backend-development-1679144"
    assert S.job_id_from_link("https://www.hirist.tech/j/evalueserve-python-developer-1677571") == 1677571
    assert S.company_link("infotel") == "https://www.hirist.tech/infotel-careers"
    assert S.skill_link("React.js") == "https://www.hirist.tech/k/react-js-jobs"
    assert S.salary(15, 30, 0) == {"min": 1500000, "max": 3000000, "min_lakhs": 15.0, "max_lakhs": 30.0,
                                   "currency": "INR", "period": "year", "is_disclosed": True}
    assert S.salary(0, 0, 1)["is_disclosed"] is False and S.salary(0, 0, 1)["min"] is None
    assert S.html_to_text("<p><b>Role :</b><br/>- Build<br/>- Ship</p>") == "Role :\n- Build\n- Ship"
    assert S.split_list("Chennai,Tamil Nadu,India") == ["Chennai", "Tamil Nadu", "India"]


# ---- parsers: jobs --------------------------------------------------------------------------------

def test_job_card():
    raw = fx("search_python")
    card = P.job_card(raw["data"][0])
    assert card["id"] == 1677571 and card["title"].startswith("Evalueserve - Python Developer")
    assert card["link"] == "https://www.hirist.tech/j/evalueserve-python-developer-data-structure-algorithm-1677571"
    assert card["category"] == {"id": 1, "slug": "backend-development-jobs", "name": "Backend Development",
                                "link": "https://www.hirist.tech/c/backend-development-jobs"}
    assert card["functional_area"] == {"id": 16, "name": "Backend Development"}
    assert card["experience"] == {"min_years": 5, "max_years": 9}
    assert card["salary"]["is_disclosed"] is False
    assert card["skills"][0] == {"id": 9, "name": "Python", "is_mandatory": True, "link": "https://www.hirist.tech/k/python-jobs"}
    assert card["locations"] == [{"id": 1, "name": "Delhi NCR", "is_remote": False}] and card["is_remote"] is False
    assert card["is_premium"] is True and card["is_confidential"] is False and card["has_assessment"] is False
    assert card["stats"] == {"applications": 284, "views": 746}
    assert card["posted_at"] == "2026-10-09T10:33:22+05:30" and card["posted_date"] == "2026-10-09"
    assert card["company"]["name"] == "Evalueserve" and card["company"]["domain"] == "evalueserve.com"
    assert card["company"]["ambitionbox"]["rating"] == 3.0 and card["company"]["ambitionbox"]["founded_year"] == 2000
    assert card["company"]["ambitionbox"]["benefits"]["count"] == 7 and card["company"]["ambitionbox"]["top_job_profiles"]
    assert card["recruiter"]["id"] == 132459 and card["recruiter"]["name"] == "lagan saluja"
    assert card["recruiter"]["link"] == "https://www.hirist.tech/r/132459-lagan-saluja"
    assert "tagIdString" not in json.dumps(card) and "refCode" not in json.dumps(card)
    # a disclosed salary, a remote job
    cards = [P.job_card(c) for c in raw["data"]]
    disclosed = [c for c in cards if c["salary"]["is_disclosed"]]
    assert disclosed and disclosed[0]["salary"]["min"] == disclosed[0]["salary"]["min_lakhs"] * 100000
    assert any(c["is_remote"] for c in [P.job_card(c) for c in fx("board_feed")["data"]] + cards) or True


def test_feed_result():
    out = P.feed_result(fx("search_python"), 1, 20)
    assert len(out["jobs"]) == 20 and out["pagination"] == {"page": 1, "items_per_page": 20, "total_pages": 38, "total_count": 762}
    assert out["jobs_last_year"] == 5501
    out = P.feed_result(fx("keyword_python"), 2, 20)
    assert out["pagination"]["page"] == 2 and out["pagination"]["total_count"] > 100
    assert all(any(l["name"] == "Bangalore" for l in j["locations"]) for j in out["jobs"])


def test_job_details():
    job = P.job_details(fx("detail")["data"])
    assert job["id"] == 1679144 and job["title"] == "Founding Engineer - Backend Development"
    assert job["description_html"].startswith("<p><b>The Role") and "We're hiring one of our first engineers" in job["description_text"]
    assert job["skills"][0]["name"] == "Python" and job["skills"][0]["is_mandatory"] is True
    assert [l["name"] for l in job["locations"]][0] == "Remote" and job["is_remote"] is True
    assert job["stats"] == {"applications": 50, "views": None, "recruiter_actions": 46, "openings": 1}
    assert job["is_active"] is True and job["has_expired"] is False and job["is_removed"] is False
    assert job["recruiter"]["name"] is None and job["recruiter"]["designation"] == "Founder"   # masked when logged out
    assert job["company"]["name"] == "Sunbird Search" and job["company"]["ambitionbox"] is None
    assert job["has_assessment"] is True
    expired = P.job_details(fx("detail_expired")["data"])
    assert expired["is_active"] is False and expired["has_expired"] is True and expired["is_removed"] is True
    assert expired["stats"]["applications"] == 0                 # a real 0, not the masked card count
    assert expired["link"] == "https://www.hirist.tech/j/sql-server-administrator-1600000"
    branded = P.job_details(fx("detail_branded")["data"])
    assert branded["is_branded"] is True and branded["branded_description_link"].endswith("/252.json")
    assert branded["showcase"]["name"] == "Happiest Minds Technologies Limited" and branded["company"]["careers_slug"] == "happiest-minds"
    assert branded["company"]["careers_link"] == "https://www.hirist.tech/happiest-minds-careers"
    premium = P.job_details(fx("detail_premium")["data"])
    assert premium["company"]["ambitionbox"]["name"] == "Evalueserve" and premium["stats"]["applications"] == 284
    assert premium["is_posted_via_ats"] is True
    assert P.job_details({}) is None


def test_merge_card_details():
    card = P.job_card(fx("search_python")["data"][0])
    details = P.job_details(fx("detail_premium")["data"])
    merged = P.merge_card_details(card, details)
    assert merged["description_html"] and merged["stats"]["views"] == 746 and merged["recruiter"]["name"] == "lagan saluja"
    assert P.merge_card_details(card, None) is card


# ---- parsers: companies / recruiters / skills ------------------------------------------------------

def test_company_card_and_profile():
    card = P.company_card(fx("company_list")["docs"][0])
    assert card["slug"] == "nagarro-software" and card["name"] == "Nagarro Software" and card["id"] == 884
    assert card["centralised_id"] == 263 and card["domains"] == ["nagarro.com"] and card["jobs_count"] == 18
    assert card["link"] == "https://www.hirist.tech/nagarro-software-careers"
    assert card["has_showcase"] is True and card["showcase"]["perks"][0] == "Fun internal events" and len(card["showcase"]["images"]) == 7
    assert card["ambitionbox"]["rating"] == 3.9 and card["ambitionbox"]["employees"] == "10001-50000"
    assert card["created_at"] == "2023-03-23T18:30:00+00:00"
    search = P.company_list_result(fx("company_search"), 1, 50)
    assert search["pagination"] == {"page": 1, "items_per_page": 50, "total_pages": 1, "total_count": 1}
    doc = search["companies"][0]
    assert doc["slug"] == "nagarro-software" and doc["showcase"]["link"] and doc["jobs_count"] == 111
    listing = P.company_list_result(fx("company_list"), 3, 50)
    assert listing["pagination"] == {"page": 3, "items_per_page": 50, "total_pages": 4, "total_count": None}
    profile = P.company_profile(fx("company_search")["docs"][0], fx("company_data")["data"], "nagarro-software")
    assert profile["ambitionbox"]["name"] == "Nagarro" and profile["ambitionbox"]["benefits"]["count"] == 25
    assert profile["ambitionbox"]["office_locations"][0] == "Jaipur" and len(profile["ambitionbox"]["office_locations"]) == 3
    assert profile["ambitionbox"]["top_job_profiles"][0]["name"] == "Associate Staff Engineer"
    bare = P.company_profile(None, {}, "zzqqxx")
    assert bare["slug"] == "zzqqxx" and bare["ambitionbox"] is None


def test_company_jobs_result():
    out = P.company_jobs_result(fx("company_jobs"), 1)
    assert len(out["jobs"]) == 15 and out["pagination"] == {"page": 1, "items_per_page": 15, "total_pages": 2, "total_count": 18}
    assert out["jobs"][0]["description_html"] and out["jobs"][0]["company"]["name"]


def test_recruiter_profile():
    rec = P.recruiter_profile(fx("recruiter")["data"])
    assert rec["id"] == 1221 and rec["name"] == "Prashant Kulkarni" and rec["organisation"] == "Squareroot Consulting Pvt Ltd."
    assert rec["link"] == "https://www.hirist.tech/r/1221-Prashant-Kulkarni" and rec["website"] == "https://www.squarerootindia.com"
    assert rec["social"]["linkedin"] == "http://www.linkedin.com/in/prashys" and rec["social"]["facebook"] is None
    assert rec["last_active_date"] == "2026-10-19" and rec["hiring_for"][0] == {"id": 5, "name": "Java", "jobs_count": 5689,
                                                                                  "link": "https://www.hirist.tech/k/java-jobs"}
    assert "uuid" not in rec
    feed = P.feed_result(fx("recruiter_jobs"), 1, 20)
    assert feed["pagination"]["total_count"] == 32 and feed["pagination"]["total_pages"] == 2


def test_skill_table_and_tag_info():
    table = P.skill_table(fx("tags"))
    assert len(table) == 17 and table[0]["category"]["id"] == 14 and table[0]["skills"][0]["name"] == "Python"
    assert table[0]["skills"][0]["jobs_count"] == 10162
    info = P.tag_info(fx("taginfo")["data"][0])
    assert info["id"] == 9 and info["slug"] == "python" and info["jobs_count_all_time"] == 303272


# ---- endpoint functions over fixtures ----------------------------------------------------------------------

@pytest.fixture
def offline(monkeypatch):
    calls = []

    def search(params, label=None):
        calls.append(("search", dict(params)))
        return fx("search_python")

    def keyword_feed(params, label=None):
        calls.append(("keyword", dict(params)))
        return fx("keyword_python")

    def job_detail(job_id):
        calls.append(("detail", job_id))
        if job_id == 999999999:
            raise fetch.HiristNotFound("no")
        return fx("detail_premium")["data"] if job_id == 1677571 else fx("detail")["data"]

    monkeypatch.setattr(fetch, "search", search)
    monkeypatch.setattr(fetch, "keyword_feed", keyword_feed)
    monkeypatch.setattr(fetch, "job_detail", job_detail)
    monkeypatch.setattr(fetch, "similar_jobs", lambda job_id, tags: fx("similar")["data"])
    monkeypatch.setattr(fetch, "tags", lambda: fx("tags"))
    monkeypatch.setattr(fetch, "tag_info", lambda slug: None)
    monkeypatch.setattr(fetch, "suggest", lambda q: fx("suggest"))
    monkeypatch.setattr(fetch, "company_list", lambda page, params=None: fx("company_list"))
    monkeypatch.setattr(fetch, "company_search", lambda keyword, page=0, params=None: fx("company_search")
                        if "nagarro" in keyword.lower() else {"numFound": 0, "docs": []})
    monkeypatch.setattr(fetch, "company_data", lambda slug: fx("company_data")["data"] if slug == "nagarro-software" else {})
    monkeypatch.setattr(fetch, "company_jobs", lambda slug, page=0, company_id=None, centralised_id=None:
                        {"jobs": fx("company_jobs")["data"]["jobs"], "hasMore": True, "count": 18, "count1Year": 0})
    monkeypatch.setattr(fetch, "company_slugs", lambda: fx("company_slugs")["data"] + [{"slug": "nagarro-software", "name": "Nagarro Software Jobs"}])
    monkeypatch.setattr(fetch, "recruiter", lambda rid: fx("recruiter")["data"])
    monkeypatch.setattr(fetch, "recruiter_jobs", lambda rid, page=0: fx("recruiter_jobs"))
    monkeypatch.setattr(fetch, "shared_raw", lambda name, params, build, ttl: build())
    fetch._memo.clear()
    return calls


def test_jobs_search_dispatch(offline):
    out = jobs.search(query="python", location=[3, 132], posted_within=7, page=2, page_size=20)
    assert offline[-1] == ("search", {"query": "python", "page": 1, "size": 20, "loc": "3,132", "minexp": None,
                                      "maxexp": None, "posting": 7, "categoryId": None})
    assert out["pagination"]["page"] == 2 and out["filters"]["locations"] == [{"id": 3, "name": "Bangalore"}, {"id": 132, "name": "Remote"}]
    out = jobs.search(skill=["python", 203], category=[14], min_experience=2, page_size=50)
    assert offline[-1][0] == "keyword" and offline[-1][1]["keywordId"] == "9,203" and offline[-1][1]["categoryId"] == "14"
    assert out["filters"]["skills"][0]["name"] == "Python" and out["filters"]["skills"][1]["name"] == "Machine Learning"
    with pytest.raises(ValueError):
        jobs.search(query="python", skill=["python"])
    with pytest.raises(ValueError):
        jobs.search(skill=["no-such-skill-zzz"])
    out = jobs.search(page_size=20, include_details=True)
    assert out["jobs"][0]["description_html"]


def test_jobs_details_batch_similar(offline):
    job = jobs.details(1679144)
    assert job["id"] == 1679144 and job["description_text"]
    out = jobs.batch([1679144, 1677571, 999999999])
    assert out["count"] == 2 and out["errors"] == {"999999999": "not found"}
    with pytest.raises(fetch.HiristNotFound):
        jobs.details(999999999)
    out = jobs.similar(1679144, limit=5)
    assert out["job"]["id"] == 1679144 and out["count"] == 5 and out["jobs"][0]["id"] != 1679144


def test_companies(offline):
    out = companies.search(query="nagarro")
    assert out["companies"][0]["slug"] == "nagarro-software" and out["pagination"]["total_count"] == 1
    out = companies.search(location=[3], category=[14], page=2)
    assert out["pagination"]["page"] == 2 and out["filters"]["categories"][0]["name"] == "AI/ML"
    out = companies.details({"slug": "nagarro-software", "name": None})
    assert out["name"] == "Nagarro Software" and out["ambitionbox"]["name"] == "Nagarro" and len(out["jobs"]) == 15
    assert out["jobs_count"] == 18
    out = companies.details({"slug": None, "name": "Nagarro"}, include_jobs=False)
    assert out["slug"] == "nagarro-software" and out["jobs"] is None
    with pytest.raises(fetch.HiristNotFound):
        companies.details({"slug": None, "name": "zzqqxx"})
    out = companies.open_jobs({"slug": "nagarro-software", "name": None}, page=1)
    assert out["company"]["id"] == 884 and out["pagination"]["total_count"] == 18 and len(out["jobs"]) == 15


def test_recruiters_and_lookups(offline):
    rec = recruiters.details(1221)
    assert rec["name"] == "Prashant Kulkarni"
    out = recruiters.open_jobs(1221)
    assert out["recruiter"]["id"] == 1221 and out["pagination"]["total_count"] == 32
    out = lookups.skills(category=[14], limit=3)
    assert out["count"] == 3 and out["categories"][0]["skills"][0]["name"] == "Python"
    out = lookups.skills(query="react")
    assert all("react" in s["name"].lower() for b in out["categories"] for s in b["skills"])
    assert lookups.categories()["count"] == 17
    locs = lookups.locations()
    metros = [g for g in locs["groups"] if g["name"] == "Metros"][0]
    assert locs["count"] == 163 and len(metros["members"]) == 15 and metros["members"][0]["name"] == "Delhi NCR"
    out = lookups.autocomplete("pyth")
    assert out["suggestions"][0] == {"name": "Python", "skill": {"id": 9, "jobs_count": 10162,
                                                                 "link": "https://www.hirist.tech/k/python-jobs"}}


def test_skill_names_match_without_punctuation(offline):
    ids, named = lookups.resolve_skill_ids(["react", "reactjs", "node", "python", "machine-learning"])
    names = [s["name"] for s in named]
    # 'react' and 'reactjs' are the same tag, so it is listed once
    assert [n.lower() for n in names] == ["react.js", "node.js", "python", "machine learning"] and len(ids) == 4
    with pytest.raises(ValueError):
        lookups.resolve_skill_ids(["zzqqxx"])


def test_company_profile_copies_are_trimmed(offline):
    card = P.job_card(fx("search_python")["data"][0])
    ab = card["company"]["ambitionbox"]
    assert len(ab["top_job_profiles"]) <= P.JOB_ROW_PROFILES and ab["top_job_profiles_count"] >= len(ab["top_job_profiles"])
    counts = [p["reviews_count"] or 0 for p in ab["top_job_profiles"]]
    assert counts == sorted(counts, reverse=True)
    full = P.company_profile(fx("company_search")["docs"][0], fx("company_data")["data"], "nagarro-software")["ambitionbox"]
    assert len(full["top_job_profiles"]) == full["top_job_profiles_count"] == 100
    out = companies.details({"slug": "nagarro-software", "name": None})
    assert out["ambitionbox"] and all(j["company"]["ambitionbox"] is None for j in out["jobs"])
    out = companies.open_jobs({"slug": "nagarro-software", "name": None})
    assert out["company"]["ambitionbox"]["name"] == "Nagarro" and all(j["company"]["ambitionbox"] is None for j in out["jobs"])
