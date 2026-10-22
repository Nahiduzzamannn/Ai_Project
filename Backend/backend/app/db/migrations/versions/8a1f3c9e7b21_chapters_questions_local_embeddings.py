"""chapters, question bank, switch to 384-dim local embeddings

Revision ID: 8a1f3c9e7b21
Revises: 5d05917e194e
Create Date: 2026-10-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy


# revision identifiers, used by Alembic.
revision: str = '8a1f3c9e7b21'
down_revision: Union[str, Sequence[str], None] = '5d05917e194e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Old 1536-dim OpenAI embeddings can't be converted; drop them and re-embed
    # with POST /api/v1/documents/{id}/reindex.
    op.drop_column('document_chunks', 'embedding')
    op.add_column('document_chunks', sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True))

    op.create_table('chapters',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('order_index', sa.Integer(), nullable=False),
    sa.Column('start_page', sa.Integer(), nullable=False),
    sa.Column('end_page', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chapters_document_id'), 'chapters', ['document_id'], unique=False)
    op.create_index(op.f('ix_chapters_id'), 'chapters', ['id'], unique=False)

    op.create_table('questions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('qtype', sa.String(length=20), nullable=False),
    sa.Column('options', sa.JSON(), nullable=True),
    sa.Column('answer', sa.Text(), nullable=True),
    sa.Column('marks', sa.Float(), nullable=False),
    sa.Column('difficulty', sa.String(length=20), nullable=False),
    sa.Column('topic', sa.String(length=255), nullable=True),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=True),
    sa.Column('chapter_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_questions_id'), 'questions', ['id'], unique=False)
    op.create_index(op.f('ix_questions_qtype'), 'questions', ['qtype'], unique=False)
    op.create_index(op.f('ix_questions_topic'), 'questions', ['topic'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_questions_topic'), table_name='questions')
    op.drop_index(op.f('ix_questions_qtype'), table_name='questions')
    op.drop_index(op.f('ix_questions_id'), table_name='questions')
    op.drop_table('questions')
    op.drop_index(op.f('ix_chapters_id'), table_name='chapters')
    op.drop_index(op.f('ix_chapters_document_id'), table_name='chapters')
    op.drop_table('chapters')
    op.drop_column('document_chunks', 'embedding')
    op.add_column('document_chunks', sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=True))
