"""semantic search

Revision ID: 5e0b7c2d9a41
Revises: 3c9e5d1a7b20
Create Date: 2026-10-22 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '5e0b7c2d9a41'
down_revision: Union[str, Sequence[str], None] = '3c9e5d1a7b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table('transaction_embeddings',
    sa.Column('transaction_id', sa.Uuid(), nullable=False),
    sa.Column('embedding', Vector(1536), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('model', sa.Text(), nullable=False),
    sa.Column('embedded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], name=op.f('fk_transaction_embeddings_transaction_id_transactions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('transaction_id', name=op.f('pk_transaction_embeddings'))
    )
    op.create_index(
        'ix_transaction_embeddings_embedding_hnsw',
        'transaction_embeddings',
        ['embedding'],
        unique=False,
        postgresql_using='hnsw',
        postgresql_with={'m': 16, 'ef_construction': 64},
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_transaction_embeddings_embedding_hnsw', table_name='transaction_embeddings', postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_table('transaction_embeddings')
    # Giữ extension `vector` (Phase 16 dùng chung); xoá thủ công nếu cần.
