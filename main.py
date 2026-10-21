"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. The inputs are resolved the same way the API resolves its
query params (hirist/refs.py): ids or links, city names, company names.
"""
import json
import os

from hirist import companies, jobs, refs

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # a job id or any hirist.tech job link
    save("job_1677866.json", jobs.details(refs.resolve_job("1677866")))

    # 20 jobs per page, filter by keyword, city, experience and posting age
    save("search_machine_learning_bangalore.json",
         jobs.search(query="machine learning", location=refs.resolve_locations("Bangalore")))

    # a company name, page slug or link
    save("company_oracle.json", companies.details(refs.resolve_company("Oracle")))
