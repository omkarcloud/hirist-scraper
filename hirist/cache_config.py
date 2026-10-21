"""Cache TTL per /hirist/* endpoint (cache.py, keyed on the validated
params — marshmallow fills the defaults, so an omitted param and its default
share a row).

hirist's feeds move hourly (new ads, refreshes, premium re-ranking); one ad
changes rarely once posted (its application count daily); company and
recruiter profiles move daily at most; the skill table's job counts move
daily; the company slug list is stable for weeks."""
from datetime import timedelta

# --- raw upstream payloads shared by several routes (fetch.shared_raw) ----------
TAGS_RAW_CACHE = timedelta(days=1)           # /tags (skill names -> ids, job counts)
COMPANY_SLUGS_RAW_CACHE = timedelta(days=7)  # /companies/slugs (name -> slug)
COMPANY_DOC_CACHE = timedelta(days=1)        # a company's directory record (ids, job count)

# --- jobs -----------------------------------------------------------------------------
SEARCH_CACHE = timedelta(hours=1)
JOB_CACHE = timedelta(hours=6)
SIMILAR_CACHE = timedelta(hours=6)

# --- companies ----------------------------------------------------------------------------
COMPANY_CACHE = timedelta(days=1)
COMPANY_SEARCH_CACHE = timedelta(hours=12)
COMPANY_JOBS_CACHE = timedelta(hours=3)

# --- recruiters ----------------------------------------------------------------------------
RECRUITER_CACHE = timedelta(days=1)
RECRUITER_JOBS_CACHE = timedelta(hours=3)

# --- lookups ------------------------------------------------------------------------------
SKILLS_CACHE = timedelta(days=1)
LOOKUPS_CACHE = timedelta(days=7)
AUTOCOMPLETE_CACHE = timedelta(days=7)
