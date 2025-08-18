# migrations/versions/add_entitlements_tables.py
"""Add entitlements tables

Revision ID: add_entitlements_tables
Revises: add_page_extraction_fields
Create Date: 2024-08-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_entitlements_tables'
down_revision = 'add_page_extraction_fields'
branch_labels = None
depends_on = None


def upgrade():
    # Create subscription_tiers table
    op.create_table('subscription_tiers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('tier', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(), nullable=True),
        sa.Column('stripe_customer_id', sa.String(), nullable=True),
        sa.Column('annual_billing', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index('idx_subscription_tier_stripe_subscription_id', 'subscription_tiers', ['stripe_subscription_id'], unique=False)
    op.create_index('idx_subscription_tier_user_id', 'subscription_tiers', ['user_id'], unique=False)

    # Create usage_metrics table
    op.create_table('usage_metrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('metric_type', sa.String(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=True),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'metric_type', 'period_start', name='unique_user_metric_period')
    )
    op.create_index('idx_usage_metrics_period', 'usage_metrics', ['period_start', 'period_end'], unique=False)
    op.create_index('idx_usage_metrics_user_id', 'usage_metrics', ['user_id'], unique=False)

    # Create credit_packs table
    op.create_table('credit_packs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('credit_type', sa.String(), nullable=False),
        sa.Column('credits_purchased', sa.Integer(), nullable=False),
        sa.Column('credits_remaining', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stripe_payment_intent_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_credit_pack_user_id', 'credit_packs', ['user_id'], unique=False)

    # Create team_workspaces table
    op.create_table('team_workspaces',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('owner_user_id', sa.Integer(), nullable=False),
        sa.Column('stripe_subscription_id', sa.String(), nullable=True),
        sa.Column('seat_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_team_workspace_owner_id', 'team_workspaces', ['owner_user_id'], unique=False)

    # Create team_memberships table
    op.create_table('team_memberships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['workspace_id'], ['team_workspaces.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'user_id', name='unique_workspace_user')
    )
    op.create_index('idx_team_membership_user_id', 'team_memberships', ['user_id'], unique=False)
    op.create_index('idx_team_membership_workspace_id', 'team_memberships', ['workspace_id'], unique=False)

    # Migrate existing subscriptions to new system
    op.execute("""
        INSERT INTO subscription_tiers (user_id, tier, status, created_at, updated_at)
        SELECT 
            us.user_id,
            CASE 
                WHEN us.plan_type = 'premium' THEN 'pro'
                WHEN us.plan_type = 'basic' THEN 'starter'
                ELSE 'free'
            END as tier,
            us.status,
            us.created_at,
            us.updated_at
        FROM user_subscriptions us
        ON CONFLICT (user_id) DO NOTHING
    """)


def downgrade():
    op.drop_index('idx_team_membership_workspace_id', table_name='team_memberships')
    op.drop_index('idx_team_membership_user_id', table_name='team_memberships')
    op.drop_table('team_memberships')
    op.drop_index('idx_team_workspace_owner_id', table_name='team_workspaces')
    op.drop_table('team_workspaces')
    op.drop_index('idx_credit_pack_user_id', table_name='credit_packs')
    op.drop_table('credit_packs')
    op.drop_index('idx_usage_metrics_user_id', table_name='usage_metrics')
    op.drop_index('idx_usage_metrics_period', table_name='usage_metrics')
    op.drop_table('usage_metrics')
    op.drop_index('idx_subscription_tier_user_id', table_name='subscription_tiers')
    op.drop_index('idx_subscription_tier_stripe_subscription_id', table_name='subscription_tiers')
    op.drop_table('subscription_tiers')