"""Add index to verification_token on token and expires_at

Revision ID: add_index_to_verification_token
Revises: <previous_revision_id>  # Replace with actual previous ID
Create Date: 2025-08-13 00:00:00.000000  # Auto-generated

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_index_to_verification_token'
down_revision = '<previous_revision_id>'  # Replace
branch_labels = None
depends_on = None

def upgrade():
    op.create_index('ix_verification_token_token_expires_at', 'verification_tokens', ['token', 'expires_at'], unique=False)

def downgrade():
    op.drop_index('ix_verification_token_token_expires_at', table_name='verification_tokens')