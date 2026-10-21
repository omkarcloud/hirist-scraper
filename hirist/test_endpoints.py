"""Live endpoint smoke tests: one call per /hirist/* route against a
running service, with example values proven to return data (2026-10-19).
The listing tooling (derive_facts.py) reads each route's FIRST call from
this file's AST as its working example, so the values stay literals.

Skipped unless HIRIST_BASE points at a running service:

    SCRAPERS_PORT=6093 ONLY_SCRAPER=hirist python run.py
    HIRIST_BASE=http://127.0.0.1:6093 python -m pytest hirist/test_endpoints.py -q
"""
import os

import pytest

BASE = os.environ.get("HIRIST_BASE", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE, reason="set HIRIST_BASE to run live endpoint tests")


def call(path, **params):
    from curl_cffi import requests
    resp = requests.get(BASE + path, params=params, timeout=300)
    assert resp.status_code == 200, f"{path} {params} -> {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body, f"{path} returned an empty body"
    return body


def status(path, **params):
    from curl_cffi import requests
    return requests.get(BASE + path, params=params, timeout=300).status_code


def test_job_search():
    body = call("/hirist/jobs/search", query="python", location="Bangalore", posted_within=30)
    assert body["count"] > 50 and body["per_page"] == 20 and len(body["jobs"]) == 20 and body["next"]
    job = body["jobs"][0]
    assert job["id"] and job["title"] and job["link"].startswith("https://www.hirist.tech/j/")
    assert job["skills"][0]["name"] and job["experience"]["max_years"] and job["posted_at"] and job["company"]["name"]
    assert body["filters"]["locations"] == [{"id": 3, "name": "Bangalore"}] and body["filters"]["posted_within_days"] == 30
    page2 = call("/hirist/jobs/search", query="python", location="Bangalore", posted_within=30, page=2)
    assert page2["current_page"] == 2 and page2["jobs"][0]["id"] not in {j["id"] for j in body["jobs"]}
    body = call("/hirist/jobs/search", skill="python,machine learning", category="ai-ml", min_experience=2,
                max_experience=6, page_size=5, include_details="true")
    assert body["count"] > 100 and len(body["jobs"]) == 5 and body["jobs"][0]["description_text"]
    assert body["filters"]["skills"][0]["name"] == "Python" and body["filters"]["categories"][0]["name"] == "AI/ML"
    body = call("/hirist/jobs/search", location="remote", page_size=50)
    assert len(body["jobs"]) == 50 and all(j["is_remote"] for j in body["jobs"])
    body = call("/hirist/jobs/search", page_size=5)
    assert body["count"] > 10000 and body["filters"]["query"] is None
    assert status("/hirist/jobs/search", query="python", skill="python") == 400
    assert status("/hirist/jobs/search", skill="zzqqxx-not-a-skill") == 400
    assert status("/hirist/jobs/search", location="Atlantis") == 400
    assert status("/hirist/jobs/search", posted_within=5) == 400


def test_job_details():
    listing = call("/hirist/jobs/search", query="python", location="Bangalore", page_size=3)
    job = listing["jobs"][0]
    body = call("/hirist/jobs/details", job=job["link"])
    assert body["id"] == job["id"] and body["description_html"] and body["description_text"]
    assert body["is_active"] is True and body["stats"]["applications"] is not None and body["recruiter"]["id"]
    assert body["company"]["name"] and body["category"]["slug"] and body["salary"]["currency"] == "INR"
    removed = call("/hirist/jobs/details", job=1600000)
    assert removed["is_active"] is False and removed["has_expired"] is True
    assert status("/hirist/jobs/details", job=999999999) == 404
    assert status("/hirist/jobs/details", job="abc") == 400


def test_job_batch_and_similar():
    listing = call("/hirist/jobs/search", query="react", location="Pune", page_size=3)
    ids = [j["id"] for j in listing["jobs"][:3]]
    body = call("/hirist/jobs/batch", jobs=",".join(str(i) for i in ids + [999999999]))
    assert body["count"] == 3 and body["errors"] == {"999999999": "not found"}
    body = call("/hirist/jobs/similar", job=ids[0], limit=5)
    assert body["job"]["id"] == ids[0] and body["count"] == 5 and body["jobs"][0]["link"]


def test_company_search():
    body = call("/hirist/companies/search", query="nagarro")
    assert body["count"] >= 1 and body["companies"][0]["slug"] == "nagarro-software" and body["companies"][0]["domains"]
    body = call("/hirist/companies/search", location="Bangalore", category="ai-ml", page=2)
    assert body["current_page"] == 2 and len(body["companies"]) == 50 and body["next"] and body["companies"][0]["link"]


def test_company_details_and_jobs():
    body = call("/hirist/companies/details", company="https://www.hirist.tech/nagarro-software-careers")
    assert body["slug"] == "nagarro-software" and body["name"] == "Nagarro Software" and body["id"] == 884
    assert body["ambitionbox"]["rating"] and body["ambitionbox"]["benefits"]["items"] and body["showcase"]["perks"]
    assert len(body["jobs"]) == 15 and body["jobs_count"] >= 15
    body = call("/hirist/companies/details", company="Infotel", include_jobs="false")
    assert body["slug"] == "infotel" and body["name"] == "Infotel" and body["jobs"] is None and body["ambitionbox"]["headquarters"]
    assert status("/hirist/companies/details", company="zzqqxx nonexistent corp") == 404
    body = call("/hirist/companies/jobs", company="nagarro-software", page=2)
    assert body["count"] >= 15 and body["per_page"] == 15 and body["company"]["slug"] == "nagarro-software" and body["jobs"]


def test_recruiters():
    body = call("/hirist/recruiters/details", recruiter="https://www.hirist.tech/r/1221-prashys-gmail-com")
    assert body["id"] == 1221 and body["name"] == "Prashant Kulkarni" and body["hiring_for"][0]["jobs_count"]
    assert body["link"] == "https://www.hirist.tech/r/1221-Prashant-Kulkarni" and body["last_active_date"]
    body = call("/hirist/recruiters/jobs", recruiter=1221)
    assert body["count"] >= 1 and body["recruiter"]["id"] == 1221 and body["jobs"][0]["recruiter"]["id"] == 1221
    assert status("/hirist/recruiters/details", recruiter=999999999) == 404


def test_lookups():
    body = call("/hirist/skills", category="ai-ml", limit=5)
    assert body["count"] == 5 and body["categories"][0]["skills"][0]["name"] == "Python" and body["categories"][0]["skills"][0]["jobs_count"]
    body = call("/hirist/skills", query="react")
    assert body["count"] > 3 and all("react" in s["name"].lower() for c in body["categories"] for s in c["skills"])
    body = call("/hirist/categories")
    assert body["count"] == 17 and body["categories"][0]["slug"] == "backend-development-jobs"
    body = call("/hirist/locations")
    assert body["count"] == 163 and body["locations"][2]["name"] == "Bangalore" and body["groups"]
    body = call("/hirist/autocomplete", query="pyth")
    assert body["suggestions"][0]["name"] == "Python" and body["suggestions"][0]["skill"]["id"] == 9
    assert status("/hirist/autocomplete") == 400
