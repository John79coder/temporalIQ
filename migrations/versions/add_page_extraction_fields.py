"""Add page extraction fields to task_candidates

Revision ID: add_page_extraction_fields
Revises: <previous_revision_id>  # Replace with actual previous ID
Create Date: 2024-07-27 00:00:00.000000  # Auto-generated

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_page_extraction_fields'
down_revision = None  # Replace with previous
branch_labels = None
depends_on = None

def upgrade():
    # NEW: Add columns for page extraction
    op.add_column('task_candidates', sa.Column('page_id', sa.String(), nullable=True))
    op.add_column('task_candidates', sa.Column('source_block_ids', sa.ARRAY(sa.String()), nullable=True))
    op.add_column('task_candidates', sa.Column('verified', sa.Boolean(), nullable=False, server_default=sa.text('false')))

def downgrade():
    # NEW: Drop columns for rollback
    op.drop_column('task_candidates', 'verified')
    op.drop_column('task_candidates', 'source_block_ids')
    op.drop_column('task_candidates', 'page_id')