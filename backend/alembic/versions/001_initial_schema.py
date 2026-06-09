"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_system_settings_key", "system_settings", ["key"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_path", sa.String(length=1024), nullable=False),
        sa.Column("library_path", sa.String(length=1024), nullable=False),
        sa.Column("cron_expr", sa.String(length=64), nullable=False),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("use_global_scrape_config", sa.Boolean(), nullable=False),
        sa.Column("scrape_options", sa.JSON(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "media_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("media_type", sa.String(length=16), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("original_title", sa.String(length=512), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("overview", sa.Text(), nullable=True),
        sa.Column("poster_path", sa.String(length=512), nullable=True),
        sa.Column("backdrop_path", sa.String(length=512), nullable=True),
        sa.Column("logo_path", sa.String(length=512), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("scrape_status", sa.String(length=32), nullable=False),
        sa.Column("match_status", sa.String(length=16), nullable=False),
        sa.Column("match_confidence", sa.Float(), nullable=True),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manual_matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_media_items_media_type", "media_items", ["media_type"])
    op.create_index("ix_media_items_tmdb_id", "media_items", ["tmdb_id"])
    op.create_index("ix_media_items_scrape_status", "media_items", ["scrape_status"])

    op.create_table(
        "cache_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cache_key", sa.String(length=512), nullable=False),
        sa.Column("cache_value", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cache_key"),
    )
    op.create_index("ix_cache_entries_cache_key", "cache_entries", ["cache_key"])

    op.create_table(
        "task_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_runs_task_id", "task_runs", ["task_id"])

    op.create_table(
        "scrape_field_statuses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("media_item_id", sa.String(length=36), nullable=False),
        sa.Column("field_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["media_item_id"], ["media_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scrape_field_statuses_media_item_id", "scrape_field_statuses", ["media_item_id"])
    op.create_index("ix_scrape_field_statuses_field_key", "scrape_field_statuses", ["field_key"])

    op.create_table(
        "source_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("media_item_id", sa.String(length=36), nullable=True),
        sa.Column("source_path", sa.String(length=2048), nullable=False),
        sa.Column("library_path", sa.String(length=2048), nullable=True),
        sa.Column("link_type", sa.String(length=16), nullable=True),
        sa.Column("file_status", sa.String(length=16), nullable=False),
        sa.Column("parsed_title", sa.String(length=512), nullable=True),
        sa.Column("parsed_year", sa.Integer(), nullable=True),
        sa.Column("parsed_season", sa.Integer(), nullable=True),
        sa.Column("parsed_episode", sa.Integer(), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("file_mtime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["media_item_id"], ["media_items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_path"),
    )
    op.create_index("ix_source_files_media_item_id", "source_files", ["media_item_id"])

    op.create_table(
        "seasons",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("media_item_id", sa.String(length=36), nullable=False),
        sa.Column("season_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("overview", sa.Text(), nullable=True),
        sa.Column("poster_path", sa.String(length=512), nullable=True),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["media_item_id"], ["media_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_seasons_media_item_id", "seasons", ["media_item_id"])

    op.create_table(
        "match_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("media_item_id", sa.String(length=36), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=False),
        sa.Column("tmdb_type", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("operator", sa.String(length=128), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["media_item_id"], ["media_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_match_history_media_item_id", "match_history", ["media_item_id"])

    op.create_table(
        "episodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("season_id", sa.String(length=36), nullable=False),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("overview", sa.Text(), nullable=True),
        sa.Column("still_path", sa.String(length=512), nullable=True),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("air_date", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_episodes_season_id", "episodes", ["season_id"])


def downgrade() -> None:
    op.drop_table("episodes")
    op.drop_table("match_history")
    op.drop_table("seasons")
    op.drop_table("source_files")
    op.drop_table("scrape_field_statuses")
    op.drop_table("task_runs")
    op.drop_table("cache_entries")
    op.drop_table("media_items")
    op.drop_table("tasks")
    op.drop_table("system_settings")
