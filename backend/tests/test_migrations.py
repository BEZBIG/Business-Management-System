"""Тест конвенции таймстампов: TimestampMixin объявляет created_at/updated_at как timezone-aware."""

from __future__ import annotations


def test_timestamp_columns_are_tz() -> None:
    """TimestampMixin должен объявлять created_at и updated_at как DateTime(timezone=True)."""
    from sqlalchemy import DateTime  # noqa: PLC0415
    from sqlalchemy.orm import MappedColumn  # noqa: PLC0415

    from app.db.base import TimestampMixin  # noqa: PLC0415

    for col_name in ("created_at", "updated_at"):
        attr = getattr(TimestampMixin, col_name, None)
        assert attr is not None, (
            f"TimestampMixin is missing column {col_name!r}. Add it with DateTime(timezone=True)."
        )

        if isinstance(attr, MappedColumn):
            col_type = attr.column.type
        else:
            try:
                col_type = attr.property.columns[0].type
            except AttributeError:
                col_type = attr.expression.type  # type: ignore[attr-defined]

        assert isinstance(col_type, DateTime), (
            f"TimestampMixin.{col_name} must use DateTime type, got {type(col_type).__name__!r}"
        )
        assert col_type.timezone is True, (
            f"TimestampMixin.{col_name} must use DateTime(timezone=True) "
            f"(TIMESTAMPTZ in PostgreSQL). Got timezone={col_type.timezone!r}."
        )
