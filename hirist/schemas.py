"""Marshmallow request schemas for every /hirist/* route.

Generic fields live in the shared top-level schema_fields.py; this module
adds the hirist resolvers (refs.py). Every schema's load() output is the
kwargs dict its endpoint function takes.

ONE param per input (tripadvisor QueryOrLinkField convention, never a
sibling `url`/`id` pair): `job` takes a job id OR any hirist job link;
`company` a page slug, a /<slug>-careers link or a company name;
`recruiter` an id or a profile link; `location` the picker's names or ids
(alternate spellings, "remote", the umbrella groups, comma list);
`category` ids, slugs or names; `skill` tag names or ids (comma lists).
"""
from marshmallow import ValidationError, fields, validate, validates_schema

from schema_fields import BaseSchema, ChoiceField, Flag, PageField, PageSizeField, QueryField, RefField, StrippedString
from hirist import refdata, refs


def _max_length(n):
    """validate.Length(max=n) that tolerates the None StrippedString returns
    for an empty value (marshmallow runs validators on it; len(None) is a 500)."""
    def check(value):
        if value is not None and len(value) > n:
            raise ValidationError(f"Longer than maximum length {n}.")
    return check


class _OptionalRef(RefField):
    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)


class JobField(RefField):
    resolver = staticmethod(refs.resolve_job)


class JobListField(RefField):
    resolver = staticmethod(refs.resolve_jobs)


class CompanyField(RefField):
    resolver = staticmethod(refs.resolve_company)


class RecruiterField(RefField):
    resolver = staticmethod(refs.resolve_recruiter)


class LocationListField(_OptionalRef):
    resolver = staticmethod(refs.resolve_locations)


class CategoryListField(_OptionalRef):
    resolver = staticmethod(refs.resolve_categories)


class SkillListField(_OptionalRef):
    resolver = staticmethod(refs.resolve_skills)


class ExperienceYearsField(fields.Integer):
    def __init__(self, **kwargs):
        kwargs.setdefault("load_default", None)
        kwargs.setdefault("validate", validate.Range(min=0, max=refdata.MAX_EXPERIENCE_YEARS))
        super().__init__(strict=False, **kwargs)


class PostedWithinField(fields.Integer):
    """Days: the site's own windows (3, 7, 15, 30, 90)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("load_default", None)
        kwargs.setdefault("validate", validate.OneOf(list(refdata.POSTING_WINDOWS)))
        super().__init__(strict=False, **kwargs)


# ---- jobs ----------------------------------------------------------------------------------------------------

class JobSearchSchema(BaseSchema):
    query = StrippedString(required=False, load_default=None, validate=_max_length(200))
    skill = SkillListField()
    category = CategoryListField()
    location = LocationListField()
    min_experience = ExperienceYearsField()
    max_experience = ExperienceYearsField()
    posted_within = PostedWithinField()
    page = PageField(max_page=refdata.MAX_PAGE)
    page_size = PageSizeField(default=refdata.PAGE_SIZE, max_size=refdata.MAX_PAGE_SIZE)
    include_details = Flag(load_default=False)

    @validates_schema
    def _check(self, data, **kwargs):
        lo, hi = data.get("min_experience"), data.get("max_experience")
        if lo is not None and hi is not None and lo > hi:
            raise ValidationError("Must not exceed max_experience.", "min_experience")


class JobSchema(BaseSchema):
    job = JobField()


class JobBatchSchema(BaseSchema):
    jobs = JobListField()


class SimilarJobsSchema(BaseSchema):
    job = JobField()
    limit = fields.Integer(load_default=20, strict=False, validate=validate.Range(min=1, max=refdata.SIMILAR_LIMIT))


# ---- companies ----------------------------------------------------------------------------------------------------

class CompanySearchSchema(BaseSchema):
    query = StrippedString(required=False, load_default=None, validate=_max_length(100))
    location = LocationListField()
    category = CategoryListField()
    page = PageField(max_page=refdata.MAX_PAGE)


class CompanySchema(BaseSchema):
    company = CompanyField()
    include_jobs = Flag(load_default=True)


class CompanyJobsSchema(BaseSchema):
    company = CompanyField()
    page = PageField(max_page=refdata.MAX_PAGE)


# ---- recruiters ----------------------------------------------------------------------------------------------------

class RecruiterSchema(BaseSchema):
    recruiter = RecruiterField()


class RecruiterJobsSchema(BaseSchema):
    recruiter = RecruiterField()
    page = PageField(max_page=refdata.MAX_PAGE)


# ---- lookups ------------------------------------------------------------------------------------------------------------

class SkillsSchema(BaseSchema):
    category = CategoryListField()
    query = StrippedString(required=False, load_default=None, validate=_max_length(80))
    limit = fields.Integer(load_default=None, strict=False, validate=validate.Range(min=1, max=1000))


class AutocompleteSchema(BaseSchema):
    query = QueryField(max_length=100)
    limit = fields.Integer(load_default=10, strict=False, validate=validate.Range(min=1, max=50))


class EmptySchema(BaseSchema):
    pass
