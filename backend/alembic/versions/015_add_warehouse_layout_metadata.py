"""Add warehouse layout metadata fields.

Revision ID: 015
Revises: 014
Create Date: 2026-05-08
"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


json_type = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    zone_columns = {column["name"] for column in inspector.get_columns("zones")}
    location_columns = {column["name"] for column in inspector.get_columns("locations")}
    if "zone_type" not in zone_columns:
        op.add_column("zones", sa.Column("zone_type", sa.String(length=40), nullable=True))
    if "coordinate_x" not in zone_columns:
        op.add_column("zones", sa.Column("coordinate_x", sa.Numeric(10, 3), nullable=True))
    if "coordinate_y" not in zone_columns:
        op.add_column("zones", sa.Column("coordinate_y", sa.Numeric(10, 3), nullable=True))
    if "coordinate_z" not in zone_columns:
        op.add_column("zones", sa.Column("coordinate_z", sa.Numeric(10, 3), nullable=True))
    if "dimensions" not in zone_columns:
        op.add_column("zones", sa.Column("dimensions", json_type, nullable=True))
    if "layout_metadata" not in zone_columns:
        op.add_column("zones", sa.Column("layout_metadata", json_type, nullable=True))
    if "drawing_source" not in zone_columns:
        op.add_column("zones", sa.Column("drawing_source", json_type, nullable=True))
    op.execute("UPDATE zones SET zone_type = 'storage' WHERE zone_type IS NULL")
    op.alter_column("zones", "zone_type", nullable=False, server_default="storage")

    if "dimensions" not in location_columns:
        op.add_column("locations", sa.Column("dimensions", json_type, nullable=True))
    if "layout_metadata" not in location_columns:
        op.add_column("locations", sa.Column("layout_metadata", json_type, nullable=True))
    if "drawing_source" not in location_columns:
        op.add_column("locations", sa.Column("drawing_source", json_type, nullable=True))
    if "wcs_point_metadata" not in location_columns:
        op.add_column("locations", sa.Column("wcs_point_metadata", json_type, nullable=True))


def downgrade() -> None:
    op.drop_column("locations", "wcs_point_metadata")
    op.drop_column("locations", "drawing_source")
    op.drop_column("locations", "layout_metadata")
    op.drop_column("locations", "dimensions")

    op.drop_column("zones", "drawing_source")
    op.drop_column("zones", "layout_metadata")
    op.drop_column("zones", "dimensions")
    op.drop_column("zones", "coordinate_z")
    op.drop_column("zones", "coordinate_y")
    op.drop_column("zones", "coordinate_x")
    op.drop_column("zones", "zone_type")
