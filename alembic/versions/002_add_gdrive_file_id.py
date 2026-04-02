"""Add gdrive_file_id to samples table.

Audio files are now stored on Google Drive instead of Supabase Storage.
gdrive_file_id stores the Drive file ID for efficient deletion during pruning.
file_url continues to hold the public download URL (now a GDrive URL for new
samples; existing Supabase URLs remain valid until pruned).

Revision ID: 002
Revises: 001
"""
import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "samples",
        sa.Column("gdrive_file_id", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("samples", "gdrive_file_id")
