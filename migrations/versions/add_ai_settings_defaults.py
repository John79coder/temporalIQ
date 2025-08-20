# migrations/versions/update_ai_settings_defaults.py
"""Update AI settings defaults to all enabled

Revision ID: update_ai_settings_defaults
Revises: add_entitlements_tables
Create Date: 2024-08-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'update_ai_settings_defaults'
down_revision = 'add_entitlements_tables'
branch_labels = None
depends_on = None


def upgrade():
    # Update default values in the table schema
    op.alter_column('user_ai_settings', 'use_llm_mapping',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('true'),
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'use_learned_detector',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('true'),
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'use_spacy_heuristics',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('true'),
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'use_embedding_similarity',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('true'),
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'use_ml_prioritization',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('true'),
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'use_nlp_urgency',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('true'),
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'use_rl_optimization',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('true'),
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'urgency_learning_scope',
                    existing_type=sa.String(),
                    server_default='global',
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'duration_learning_scope',
                    existing_type=sa.String(),
                    server_default='global',
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'mapping_learning_scope',
                    existing_type=sa.String(),
                    server_default='global',
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'slot_ranking_learning_scope',
                    existing_type=sa.String(),
                    server_default='global',
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'use_nlp_scoring',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('true'),
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'use_ai_page_extraction',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('true'),
                    existing_nullable=True)

    # Update all existing records to have the new defaults where they haven't been explicitly set
    op.execute("""
               UPDATE user_ai_settings
               SET use_llm_mapping             = COALESCE(use_llm_mapping, true),
                   use_learned_detector        = COALESCE(use_learned_detector, true),
                   use_spacy_heuristics        = COALESCE(use_spacy_heuristics, true),
                   use_embedding_similarity    = COALESCE(use_embedding_similarity, true),
                   use_ml_prioritization       = COALESCE(use_ml_prioritization, true),
                   use_nlp_urgency             = COALESCE(use_nlp_urgency, true),
                   use_rl_optimization         = COALESCE(use_rl_optimization, true),
                   urgency_learning_scope      = COALESCE(urgency_learning_scope, 'global'),
                   duration_learning_scope     = COALESCE(duration_learning_scope, 'global'),
                   mapping_learning_scope      = COALESCE(mapping_learning_scope, 'global'),
                   slot_ranking_learning_scope = COALESCE(slot_ranking_learning_scope, 'global'),
                   use_nlp_scoring             = COALESCE(use_nlp_scoring, true),
                   use_ai_page_extraction      = COALESCE(use_ai_page_extraction, true),
                   updated_at                  = NOW()
               """)


def downgrade():
    # Revert to old defaults
    op.alter_column('user_ai_settings', 'use_llm_mapping',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('false'),
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'use_learned_detector',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('false'),
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'use_spacy_heuristics',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('false'),
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'use_embedding_similarity',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('false'),
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'use_ml_prioritization',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('false'),
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'use_nlp_urgency',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('false'),
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'use_rl_optimization',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('false'),
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'urgency_learning_scope',
                    existing_type=sa.String(),
                    server_default='user',
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'duration_learning_scope',
                    existing_type=sa.String(),
                    server_default='user',
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'mapping_learning_scope',
                    existing_type=sa.String(),
                    server_default='user',
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'slot_ranking_learning_scope',
                    existing_type=sa.String(),
                    server_default='user',
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'use_nlp_scoring',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('false'),
                    existing_nullable=True)
    op.alter_column('user_ai_settings', 'use_ai_page_extraction',
                    existing_type=sa.Boolean(),
                    server_default=sa.text('false'),
                    existing_nullable=True)

    # Revert existing records to old defaults
    op.execute("""
               UPDATE user_ai_settings
               SET use_llm_mapping             = false,
                   use_learned_detector        = false,
                   use_spacy_heuristics        = false,
                   use_embedding_similarity    = false,
                   use_ml_prioritization       = false,
                   use_nlp_urgency             = false,
                   use_rl_optimization         = false,
                   urgency_learning_scope      = 'user',
                   duration_learning_scope     = 'user',
                   mapping_learning_scope      = 'user',
                   slot_ranking_learning_scope = 'user',
                   use_nlp_scoring             = false,
                   use_ai_page_extraction      = false,
                   updated_at                  = NOW()
               """)