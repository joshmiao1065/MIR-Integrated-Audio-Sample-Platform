"""Add follows, user_activities, trending_cache; replace collections.is_private with visibility.

Revision ID: 003
Revises: 002
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── follows ───────────────────────────────────────────────────────────────
    op.create_table(
        "follows",
        sa.Column("follower_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("following_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("follower_id", "following_id"),
        sa.CheckConstraint("follower_id != following_id", name="ck_follows_no_self_follow"),
    )
    # PK covers (follower_id, following_id); need a separate index for reverse lookup
    op.create_index("ix_follows_following_id", "follows", ["following_id"])

    # ── user_activities ───────────────────────────────────────────────────────
    op.create_table(
        "user_activities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_type", sa.String(30), nullable=False),
        sa.Column("sample_id", UUID(as_uuid=True),
                  sa.ForeignKey("samples.id", ondelete="CASCADE"), nullable=True),
        sa.Column("activity_data", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    # Composite DESC index for feed query (user_id IN (...) ORDER BY created_at DESC)
    op.execute(
        "CREATE INDEX ix_user_activities_user_created "
        "ON user_activities (user_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_user_activities_created "
        "ON user_activities (created_at DESC)"
    )

    # ── trending_cache ────────────────────────────────────────────────────────
    op.create_table(
        "trending_cache",
        sa.Column("window_type", sa.String(20), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("sample_id", UUID(as_uuid=True),
                  sa.ForeignKey("samples.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("window_type", "rank"),
    )

    # ── collections: is_private → visibility (4-step safe migration) ──────────
    # Step 1: add nullable column
    op.add_column("collections", sa.Column("visibility", sa.String(20), nullable=True))
    # Step 2: backfill from is_private
    op.execute(
        "UPDATE collections "
        "SET visibility = CASE WHEN is_private THEN 'private' ELSE 'public' END"
    )
    # Step 3: make non-nullable with default
    op.alter_column("collections", "visibility", nullable=False, server_default="public")
    # Step 4: add check constraint
    op.create_check_constraint(
        "ck_collections_visibility", "collections",
        "visibility IN ('public', 'friends', 'private')",
    )
    # Step 5: drop old column
    op.drop_column("collections", "is_private")

    # ── Performance indexes on existing tables ────────────────────────────────
    # Needed for the weekly trending window query
    op.execute(
        "CREATE INDEX ix_download_history_downloaded_at "
        "ON download_history (downloaded_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_ratings_created_at "
        "ON ratings (created_at DESC)"
    )
    # Needed for the recommendation CTE which looks up sample_tags by tag_id
    op.create_index("ix_sample_tags_tag_id", "sample_tags", ["tag_id"])


def downgrade() -> None:
    op.drop_index("ix_sample_tags_tag_id", table_name="sample_tags")
    op.execute("DROP INDEX IF EXISTS ix_ratings_created_at")
    op.execute("DROP INDEX IF EXISTS ix_download_history_downloaded_at")

    # Restore is_private
    op.add_column("collections", sa.Column("is_private", sa.Boolean(), nullable=True))
    op.execute(
        "UPDATE collections "
        "SET is_private = CASE WHEN visibility = 'private' THEN true ELSE false END"
    )
    op.alter_column("collections", "is_private", nullable=False, server_default="false")
    op.drop_constraint("ck_collections_visibility", "collections", type_="check")
    op.drop_column("collections", "visibility")

    op.drop_table("trending_cache")
    op.execute("DROP INDEX IF EXISTS ix_user_activities_created")
    op.execute("DROP INDEX IF EXISTS ix_user_activities_user_created")
    op.drop_table("user_activities")
    op.drop_index("ix_follows_following_id", table_name="follows")
    op.drop_table("follows")
