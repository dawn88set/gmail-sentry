"""
Shared "app factory" building blocks reused across every Claritty department app.

These modules are deliberately generic so a forked app gets the common spine
(item lifecycle, human-in-the-loop approval, audit trail, integration adapters,
reusable routes) for free and only writes its thin domain delta.

Modules
-------
- spine        : reusable SQLAlchemy mixins + AuditEvent model + record_audit()
- item_routes  : make_item_router() — CRUD + approve/reject/edit + /api/widget
- adapters/    : typed wrappers over ctx.integration(...) for the demo providers

Forked apps import from here; they never copy these files.
"""
