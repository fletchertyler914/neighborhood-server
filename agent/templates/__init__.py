"""Shareable build templates (FAWE schematics + catalog metadata)."""

from agent.templates.catalog import (
    TemplateMeta,
    catalog_path,
    ensure_schematic_on_server,
    find_template,
    iter_templates,
    list_template_summaries,
    load_catalog,
    resolve_template_id,
    schematics_repo_dir,
    validate_template_id,
)

__all__ = [
    "TemplateMeta",
    "catalog_path",
    "ensure_schematic_on_server",
    "find_template",
    "iter_templates",
    "list_template_summaries",
    "load_catalog",
    "resolve_template_id",
    "schematics_repo_dir",
    "validate_template_id",
]
