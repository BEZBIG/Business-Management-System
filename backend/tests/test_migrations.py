"""
Alembic DDL timestamp convention tests — NFR-01 criterion #3.

Tests:
  test_timestamp_columns_are_tz — TimestampMixin uses DateTime(timezone=True)
                                  for all timestamp columns (TIMESTAMPTZ in PG).

Activated in plan 01-02 (Wave 2): skip decorator removed; implementation added.
"""

from __future__ import annotations


def test_timestamp_columns_are_tz() -> None:
    """TimestampMixin must declare created_at and updated_at with DateTime(timezone=True).

    NFR-01 criterion #3 — all timestamp columns must use TIMESTAMPTZ in PostgreSQL
    (mapped via SQLAlchemy DateTime(timezone=True)) to ensure timezone-aware datetimes
    throughout the application and prevent timezone comparison errors (RESEARCH.md Pitfall 6).

    This is a DDL inspection test: it imports the mixin class and inspects
    the SQLAlchemy column type directly — no database connection required.

    SQLAlchemy 2.0 mapped_column() API notes:
    - On a bare mixin (not yet mapped), getattr(TimestampMixin, col_name) returns
      a MappedColumn descriptor object, not an InstrumentedAttribute.
    - MappedColumn.column gives the underlying Column object (accessible pre-mapping).
    - We use MappedColumn.column.type for the type inspection.
    """
    from sqlalchemy import DateTime  # noqa: PLC0415
    from sqlalchemy.orm import MappedColumn  # noqa: PLC0415

    from app.db.base import TimestampMixin  # noqa: PLC0415

    # Inspect each expected timestamp column on the mixin
    for col_name in ("created_at", "updated_at"):
        attr = getattr(TimestampMixin, col_name, None)
        assert attr is not None, (
            f"TimestampMixin is missing column {col_name!r}. "
            "Add it with DateTime(timezone=True) (D-10, NFR-01 criterion #3)."
        )

        # SQLAlchemy 2.0: on a mixin class (not a mapped model), mapped_column()
        # attributes are MappedColumn descriptors.  Access the Column via .column.
        if isinstance(attr, MappedColumn):
            col_type = attr.column.type
        else:
            # Fallback for legacy mapped classes / InstrumentedAttribute
            try:
                col_type = attr.property.columns[0].type
            except AttributeError:
                col_type = attr.expression.type  # type: ignore[attr-defined]

        assert isinstance(col_type, DateTime), (
            f"TimestampMixin.{col_name} must use DateTime type, got {type(col_type).__name__!r}"
        )
        assert col_type.timezone is True, (
            f"TimestampMixin.{col_name} must use DateTime(timezone=True) "
            f"(TIMESTAMPTZ in PostgreSQL). Got timezone={col_type.timezone!r}. "
            "Fix: DateTime(timezone=True) (D-10, NFR-01 criterion #3, RESEARCH.md Pitfall 6)."
        )
