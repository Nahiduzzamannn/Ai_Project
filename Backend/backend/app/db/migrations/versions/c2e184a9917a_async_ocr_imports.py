"""Track asynchronous OCR import progress.

Revision ID: c2e184a9917a
Revises: b6934b71c201
"""

from alembic import op
import sqlalchemy as sa

revision = "c2e184a9917a"
down_revision = "b6934b71c201"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ocr_imports", sa.Column("status", sa.String(20), nullable=False, server_default="queued"))
    op.add_column("ocr_imports", sa.Column("processed_pages", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("ocr_imports", sa.Column("total_pages", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("ocr_imports", sa.Column("error", sa.Text(), nullable=True))
    op.add_column("ocr_imports", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE ocr_imports SET status = 'completed', processed_pages = json_array_length(pages), total_pages = json_array_length(pages)")
    op.alter_column("ocr_imports", "status", server_default=None)
    op.alter_column("ocr_imports", "processed_pages", server_default=None)
    op.alter_column("ocr_imports", "total_pages", server_default=None)


def downgrade():
    op.drop_column("ocr_imports", "heartbeat_at")
    op.drop_column("ocr_imports", "error")
    op.drop_column("ocr_imports", "total_pages")
    op.drop_column("ocr_imports", "processed_pages")
    op.drop_column("ocr_imports", "status")
