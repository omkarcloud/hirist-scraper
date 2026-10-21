"""/hirist/skills, /hirist/categories, /hirist/locations, /hirist/autocomplete
— the vocabularies behind the search filters (the skill table live from
the site and cached, the categories and locations from refdata) and the
search box's suggestions; plus the skill-name -> tag-id resolution the job
search uses."""
import re

from hirist import cache_config as ttl
from hirist import fetch, refdata, refs
from hirist import parsers as P
from hirist import shared as S


# ---- skills ------------------------------------------------------------------------------------------------

def skill_table():
    """The parsed /tags table (cached a day: ~7,000 skills by category)."""
    return fetch.shared_raw("skill_table", {}, lambda: P.skill_table(fetch.tags()), ttl.TAGS_RAW_CACHE)


def _norm(name):
    """'React.JS' / 'react js' / 'reactjs' -> 'reactjs' (letters and digits only;
    '+' and '#' kept so C++ / C# stay apart from C)."""
    return re.sub(r"[^a-z0-9+#]+", "", (name or "").lower())


def _skill_index():
    """lower-cased name / id -> skill, plus '~<normalized name>' keys (the
    busiest tag wins a collision) for the punctuation-insensitive fallback."""
    index = {}
    for block in skill_table():
        for skill in block["skills"]:
            key = " ".join((skill["name"] or "").lower().split())
            if key and key not in index:
                index[key] = skill
            if skill["id"] is not None:
                index.setdefault(str(skill["id"]), skill)
            norm = _norm(skill["name"])
            if norm:
                held = index.get("~" + norm)
                if held is None or (skill["jobs_count"] or 0) > (held["jobs_count"] or 0):
                    index["~" + norm] = skill
    return index


def _lookup_name(index, item):
    """A typed skill name -> its tag: the exact name, then the name without
    punctuation ('reactjs' -> 'React.js'), then the '.js' library of that
    name ('react' -> 'React.js', 'node' -> 'Node.js')."""
    hit = index.get(item)
    if hit is None:
        norm = _norm(item)
        hit = index.get("~" + norm) or (index.get("~" + norm + "js") if norm else None)
    return hit


def skill_index():
    return fetch.memoized(("skill_index",), _skill_index, ttl=fetch.MEMO_TTL)


def resolve_skill_ids(skills):
    """The validated `skill` list (names lower-cased, ids as ints) -> tag
    ids. A name missing from the table is tried as a /k/ slug (tag_info);
    still unknown -> ValueError (a 400)."""
    if not skills:
        return None, []
    index = skill_index()
    ids, refs_out = [], []
    for item in skills:
        if isinstance(item, int):
            hit = index.get(str(item)) or {"id": item, "name": None, "link": None}
        else:
            hit = _lookup_name(index, item)
            if hit is None:
                info = fetch.tag_info(S.slugify(item) or item)
                hit = P.tag_info(info) if info else None
            if hit is None or hit.get("id") is None:
                raise ValueError(f"'{item}' is not a skill hirist knows; see /hirist/skills or /hirist/autocomplete.")
        if hit["id"] not in ids:
            ids.append(hit["id"])
            refs_out.append({"id": hit["id"], "name": hit.get("name"), "link": hit.get("link")})
    return ids, refs_out


def skills(category=None, query=None, limit=None):
    """Every skill tag with its live job count, by job category. `category`
    narrows to one or more categories, `query` to names containing it,
    `limit` keeps the top-N by job count per category."""
    table = skill_table()
    needle = (query or "").lower()
    out = []
    for block in table:
        cat = block["category"] or {}
        if category and cat.get("id") not in category:
            continue
        rows = block["skills"]
        if needle:
            rows = [s for s in rows if needle in (s["name"] or "").lower()]
        rows = sorted(rows, key=lambda s: -(s["jobs_count"] or 0))
        if limit:
            rows = rows[:limit]
        out.append({"category": cat or None, "skills": rows, "count": len(rows)})
    total = sum(b["count"] for b in out)
    return {"categories": out, "count": total}


# ---- categories / locations -----------------------------------------------------------------------------

def categories():
    """The 17 job categories (the `category` filter's ids / slugs / names, the /c/ pages)."""
    rows = [P.category_ref(cid) for cid in refdata.CATEGORIES]
    return {"categories": rows, "count": len(rows)}


def locations():
    """The location picker: the `location` filter's ids and names, with the
    umbrella entries (Metros, Anywhere in India, Overseas, Delhi NCR) and
    their members."""
    groups = {gid: members for gid, members in refdata.LOCATION_GROUPS.items()}
    member_of = {}
    for gid, members in groups.items():
        for m in members:
            member_of.setdefault(m, []).append(gid)
    rows = []
    for loc_id, name in refdata.LOCATIONS.items():
        rows.append({"id": loc_id, "name": name, "is_remote": name.lower() in refdata.REMOTE_NAMES,
                     "is_group": loc_id in groups,
                     "groups": [refdata.LOCATIONS.get(gid) for gid in member_of.get(loc_id, [])]})
    group_rows = [{"id": gid, "name": refdata.LOCATIONS.get(gid),
                   "members": [{"id": m, "name": refdata.LOCATIONS.get(m)} for m in members if m in refdata.LOCATIONS]}
                  for gid, members in groups.items()]
    return {"locations": rows, "count": len(rows), "groups": group_rows}


# ---- autocomplete --------------------------------------------------------------------------------------------

def autocomplete(query, limit=10):
    """The search box's suggestions for `query` (skill and role names), each
    with the matching skill tag when the table has one."""
    names = fetch.suggest(query)[:limit]
    index = skill_index()
    out = []
    for name in names:
        hit = _lookup_name(index, " ".join(name.lower().split()))
        out.append({"name": name, "skill": {"id": hit["id"], "jobs_count": hit["jobs_count"], "link": hit["link"]}
                    if hit else None})
    return {"query": query, "suggestions": out, "count": len(out)}


def category_refs(ids):
    return [P.category_ref(c) for c in (ids or [])] or None


def location_refs(ids):
    return [{"id": i, "name": refdata.LOCATIONS.get(i)} for i in (ids or [])] or None
