# 💼 Hirist Scraper

Hirist Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Hirist IT job data for free.

## ✨ What Can I Get?

- 💼 **30,000+ live IT jobs** — full description, mandatory skills, experience, salary, applicant counts & the recruiter
- 🔍 **Search 2,100+ skills, 17 categories & 163 cities** — plus experience band, posting age & remote
- 🏢 **24,000+ company pages** — AmbitionBox rating, reviews, benefits, size, HQ, perks & every open job
- ⚡ **1,000+ new jobs every week** — each with its recruiter's profile, LinkedIn & last active date

## 🎥 Example: A Full Hirist Job

```json
{
  "id": 1677866,
  "title": "Oracle - Software Developer II - Java Technologies",
  "link": "https://www.hirist.tech/j/oracle-software-developer-ii-java-technologies-4-7-yrs-1677866",
  "category": { "id": 1, "slug": "backend-development-jobs", "name": "Backend Development" },
  "experience": { "min_years": 4, "max_years": 7 },
  "skills": [
    { "id": 5, "name": "Java", "is_mandatory": true, "link": "https://www.hirist.tech/k/java-jobs" },
    { "id": 348, "name": "Multithreading", "is_mandatory": true, "link": "https://www.hirist.tech/k/multithreading-jobs" }
  ],
  "locations": [{ "id": 3, "name": "Bangalore", "is_remote": false }],
  "stats": { "applications": 2093, "recruiter_actions": 1279, "openings": 1 },
  "posted_at": "2026-10-12T11:32:20+05:30",
  "description_text": "As a Senior Software Engineer, you will be responsible for the development and support of Java based developer platforms and common tooling ...",
  "company": {
    "name": "Oracle India",
    "domain": "oracle.com",
    "careers_link": "https://www.hirist.tech/oracle-careers",
    "ambitionbox": {
      "founded_year": 1977,
      "headquarters": "Austin,Texas",
      "employees_india": "50001-100000",
      "rating": 3.1,
      "reviews_count": 7158,
      "top_job_profiles": [{ "name": "Senior Software Engineer", "rating": 2.8, "reviews_count": 225 }]
    }
  },
  "recruiter": { "id": 207898, "designation": "TA", "link": "https://www.hirist.tech/r/207898" },
  "is_active": true
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Hirist Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/hirist-scraper
cd hirist-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/jobs/details?job=1677866"
```

```json
{
  "id": 1677866,
  "title": "Oracle - Software Developer II - Java Technologies",
  "designation": "Software Developer II",
  "link": "https://www.hirist.tech/j/oracle-software-developer-ii-java-technologies-4-7-yrs-1677866",
  "experience": { "min_years": 4, "max_years": 7 },
  "skills": [
    { "id": 5, "name": "Java", "is_mandatory": true, "link": "https://www.hirist.tech/k/java-jobs" }
  ],
  "locations": [{ "id": 3, "name": "Bangalore", "is_remote": false }],
  "stats": { "applications": 2093, "views": null, "recruiter_actions": 1279, "openings": 1 },
  "posted_at": "2026-10-12T11:32:20+05:30",
  "company": {
    "id": 34,
    "name": "Oracle India",
    "domain": "oracle.com",
    "careers_link": "https://www.hirist.tech/oracle-careers"
  },
  "is_active": true
}
```

All 13 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

13 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Job Details | `/jobs/details` | The full job ad: description, skills, applicants, recruiter, company |
| Search Jobs | `/jobs/search` | 20–50 jobs per page with every Hirist filter |
| Batch Job Details | `/jobs/batch` | Full details for up to 10 jobs in one call |
| Similar Jobs | `/jobs/similar` | The jobs Hirist recommends alongside any job |
| Company Details | `/companies/details` | AmbitionBox rating, reviews, benefits, perks and open jobs |
| Company Jobs | `/companies/jobs` | Every open job at a company, with full details |
| Search Companies | `/companies/search` | Find companies by name, or browse by city and category |
| Recruiter Details | `/recruiters/details` | Company, title, LinkedIn, last active and skills they hire |
| Recruiter Jobs | `/recruiters/jobs` | Every open job a recruiter has posted |
| Autocomplete | `/autocomplete` | Skill and role suggestions with live job counts |
| Skills | `/skills` | 2,100+ skills with live job counts, by category |
| Categories | `/categories` | All 17 job categories for the `category` filter |
| Locations | `/locations` | All 163 cities, states and regions for the `location` filter |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-hirist-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-hirist-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-hirist-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/jobs/search",
    params={"query": "machine learning", "location": "Bangalore"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Hirist Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Hirist%20Scraper%20API.)

[![Ask Us by Email about Hirist Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Hirist%20Scraper%20API&body=I%20need%20help%20using%20the%20Hirist%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**Internshala Scraper**](https://github.com/omkarcloud/internshala-scraper) — Internshala internships & jobs: stipends, CTC, skills, applicants & employer profiles
- [**IIMJobs Scraper**](https://github.com/omkarcloud/iimjobs-scraper) — iimjobs management jobs, company ratings, recruiters & executive courses
- [**Jobstreet Scraper**](https://github.com/omkarcloud/jobstreet-scraper) — JobStreet & JobsDB jobs, salaries, companies & reviews across 6 markets
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/hirist-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/hirist-scraper)
