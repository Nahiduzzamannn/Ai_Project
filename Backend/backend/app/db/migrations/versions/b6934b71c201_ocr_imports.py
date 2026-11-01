"""Store OCR imports and link accepted questions.

Revision ID: b6934b71c201
Revises: 8a1f3c9e7b21
"""
from alembic import op
import sqlalchemy as sa

revision = "b6934b71c201"
down_revision = "8a1f3c9e7b21"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ocr_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(100), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("pages", sa.JSON(), nullable=False),
        sa.Column("candidates", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("questions", sa.Column("ocr_import_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_questions_ocr_import_id", "questions", "ocr_imports", ["ocr_import_id"], ["id"], ondelete="SET NULL")


def downgrade():
    op.drop_constraint("fk_questions_ocr_import_id", "questions", type_="foreignkey")
    op.drop_column("questions", "ocr_import_id")
    op.drop_table("ocr_imports")
