"""Value helpers shared by every hirist parser: safe nested access,
numbers, text, dates, site links, salaries and HTML descriptions. Pure
functions, no network; every helper tolerates None and junk.

The generic helpers (g / as_list / as_dict, num … html_to_text) have the
same semantics as instahyre/shared.py and jobstreet/shared.py; they live
here so the hirist package stands alone (it ships as its own open-source
repo, which must not pull in other sites' modules)."""
import html as html_lib
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

from hirist import refdata

# ---- safe access ---------------------------------------------------------------------------

def g(obj, *path, default=None):
    """Safe nested get: g(d, "a", "b", 0) -> d["a"]["b"][0] or default."""
    for step in path:
        if isinstance(step, int):
            if not isinstance(obj, list) or not -len(obj) <= step < len(obj):
                return default
            obj = obj[step]
        else:
            if not isinstance(obj, dict):
                return default
            obj = obj.get(step)
        if obj is None:
            return default
    return obj


def as_list(value):
    return value if isinstance(value, list) else []


def as_dict(value):
    return value if isinstance(value, dict) else {}


# ---- numbers -------------------------------------------------------------------------------

def num(value):
    """int / float / numeric string ('1,234.5') -> float; bool, junk, NaN,
    the site's '*****' masks -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value else None
    try:
        out = float(str(value).strip().replace(",", ""))
    except ValueError:
        return None
    return out if out == out else None


def to_int(value):
    out = num(value)
    return int(round(out)) if out is not None else None


def count(value):
    """A non-negative count; negatives -> 0; the logged-out '*****' mask -> None."""
    out = to_int(value)
    if out is None:
        return None
    return out if out >= 0 else 0


def flag(value):
    """The site's 0/1 (also '0'/'1', true/false) -> bool; None stays None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "yes"):
            return True
        if low in ("false", "no", ""):
            return False
    out = to_int(value)
    return bool(out) if out is not None else None


def rating(value):
    """A 0-5 star rating rounded to 1 place; 0 / missing -> None."""
    out = num(value)
    return round(out, 1) if out else None


def year(value):
    """A founding / batch year: 4-digit int, else None (the site stores 0 for unknown)."""
    out = to_int(value)
    return out if out and 1000 <= out <= 2100 else None


# ---- text ----------------------------------------------------------------------------------

def text(value):
    """Whitespace-collapsed, HTML-unescaped string; '' / '*****' -> None."""
    if value is None or isinstance(value, bool):
        return None
    out = " ".join(html_lib.unescape(str(value)).replace("\xa0", " ").split())
    if not out or set(out) == {"*"}:
        return None
    return out


def multiline(value):
    """Like text() but keeps line breaks (descriptions)."""
    if value is None:
        return None
    lines = [" ".join(line.split()) for line in html_lib.unescape(str(value)).replace("\xa0", " ").splitlines()]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out or None


def text_list(values):
    """A list of strings, trimmed, deduped, empties dropped."""
    out = []
    for value in as_list(values):
        item = text(value)
        if item and item not in out:
            out.append(item)
    return out


def split_list(value, sep=","):
    """'Chennai,Tamil Nadu,India' / 'Pune/Indore' -> ['Chennai', 'Tamil Nadu', 'India']."""
    if isinstance(value, list):
        return text_list(value)
    value = text(value)
    if not value:
        return []
    return text_list(value.split(sep))


def lower_snake(value):
    """'Work-Life Balance' -> 'work_life_balance'."""
    value = text(value)
    if not value:
        return None
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or None


def slugify(value):
    """'Backend Development' -> 'backend-development'."""
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or None


# ---- dates -------------------------------------------------------------------------------

IST = timezone(timedelta(hours=5, minutes=30))


def iso_datetime_ms(value):
    """An epoch in milliseconds -> ISO 8601 in the site's zone
    ('2026-10-08T10:33:22+05:30'); junk -> None."""
    ms = num(value)
    if not ms or ms < 10 ** 11:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=IST).isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return None


def iso_date_ms(value):
    """An epoch in milliseconds -> the calendar date in the site's zone ('2026-10-08')."""
    stamp = iso_datetime_ms(value)
    return stamp[:10] if stamp else None


_LONG_DATE_FORMATS = ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%d/%m/%Y")


def iso_date(value):
    """'2026-10-12' / '2026-10-12T…' / 'October 12, 2026' -> 'YYYY-MM-DD'."""
    value = text(value)
    if not value:
        return None
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if match:
        return "-".join(match.groups())
    for fmt in _LONG_DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def iso_datetime(value):
    """'2023-03-23T18:30:00.000+00:00' -> '2023-03-23T18:30:00+00:00'; a bare date stays a date."""
    value = text(value)
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return iso_date(value)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.isoformat(timespec="seconds")


# ---- links -------------------------------------------------------------------------------

def link(path):
    """A site-relative path (or absolute URL) -> absolute https link; '' / None -> None."""
    path = text(path) if isinstance(path, str) else None
    if not path:
        return None
    if path.startswith("http://") and re.match(r"http://(www\.)?hirist\.", path):
        return "https://" + path[len("http://"):]       # the site's own links are http:// in places
    if path.startswith(("http://", "https://")):
        return path
    if path.startswith("//"):
        return "https:" + path
    return f"{refdata.BASE_URL}/{path.lstrip('/')}"


def is_site_link(value):
    return bool(re.match(r"https?://(www\.)?hirist\.(tech|com)/", str(value or "")))


def website(value):
    """'www.squarerootindia.com' / 'https://x.com' -> an https link; '' -> None."""
    value = text(value)
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return value
    return "https://" + value.lstrip("/")


def job_link(job_id, title=None):
    """The canonical /j/<slug>-<id> link of a job."""
    job_id = to_int(job_id)
    if not job_id:
        return None
    slug = slugify(title)
    return f"{refdata.BASE_URL}/j/{slug + '-' if slug else ''}{job_id}"


def company_link(slug):
    return f"{refdata.BASE_URL}/{slug}-careers" if slug else None


def recruiter_link(recruiter_id, name=None):
    recruiter_id = to_int(recruiter_id)
    if not recruiter_id:
        return None
    slug = slugify(name)
    return f"{refdata.BASE_URL}/r/{recruiter_id}{'-' + slug if slug else ''}"


def category_link(slug):
    return f"{refdata.BASE_URL}/c/{slug}" if slug else None


def skill_link(name):
    slug = slugify(name)
    return f"{refdata.BASE_URL}/k/{slug}-jobs" if slug else None


def job_id_from_link(value):
    """'https://www.hirist.tech/j/founding-engineer-backend-1679144' -> 1679144."""
    value = text(value)
    if not value:
        return None
    match = re.search(r"/j/(?:[^/?#]*?-)?(\d+)(?:[/?#]|$)", value)
    return int(match.group(1)) if match else None


def is_remote(locations):
    return any(text(loc).lower() in refdata.REMOTE_NAMES for loc in as_list(locations) if text(loc))


# ---- salaries -------------------------------------------------------------------------------

def salary(min_lakhs, max_lakhs, hidden):
    """The site quotes salaries in lakhs per annum and most recruiters hide
    them (hideSal=1 with min/max 0) -> {min, max (INR per year), min_lakhs,
    max_lakhs, currency, period, is_disclosed}."""
    lo, hi = num(min_lakhs), num(max_lakhs)
    disclosed = not flag(hidden) and bool(lo or hi)
    if not disclosed:
        lo = hi = None
    return {
        "min": int(round(lo * refdata.LAKH)) if lo else None,
        "max": int(round(hi * refdata.LAKH)) if hi else None,
        "min_lakhs": lo,
        "max_lakhs": hi,
        "currency": refdata.DEFAULT_CURRENCY,
        "period": "year",
        "is_disclosed": disclosed,
    }


# ---- HTML -> text ------------------------------------------------------------------------------------

_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table",
               "section", "article", "header", "footer", "blockquote", "pre", "hr", "dd", "dt", "dl"}
_SKIP_TAGS = {"script", "style", "noscript", "template", "head"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in ("li", "br"):
            return
        elif tag in ("ul", "ol"):
            self.parts.append("\n\n")      # a list ends its paragraph
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(value):
    """An HTML fragment -> readable plain text: block elements become line
    breaks, list items get a dash, runs of blank lines collapse."""
    value = value if isinstance(value, str) else None
    if not value:
        return None
    if "<" not in value:
        return multiline(value)
    parser = _TextExtractor()
    try:
        parser.feed(value)
        parser.close()
    except Exception:
        return multiline(re.sub(r"<[^>]+>", " ", value))
    raw = "".join(parser.parts).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in raw.splitlines()]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"\n\n(- )", r"\n\1", out).strip()   # list items stay tight
    return out or None


def html_fragment(value):
    """The job description as the site stores it (an HTML fragment); '' / None -> None."""
    value = value if isinstance(value, str) else None
    if not value or not value.strip():
        return None
    return value.strip()
