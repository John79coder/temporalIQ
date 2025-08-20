# app/features/services/ai_settings_config.py
from typing import Dict, Set
from dataclasses import dataclass


@dataclass
class AISettingConfig:
    """Configuration for an AI setting"""
    name: str
    display_name: str
    description: str
    tier_required: str  # Minimum tier required to customize
    category: str  # 'detection', 'learning', 'optimization'


class AISettingsConfiguration:
    """Central configuration for AI settings and tier access"""

    # Define which settings each tier can customize
    TIER_CUSTOMIZABLE_SETTINGS: Dict[str, Set[str]] = {
        'free': set(),  # Cannot customize any settings
        'starter': {
            # Basic customization
            'use_spacy_heuristics',
            'use_embedding_similarity',
            'use_nlp_urgency',
            'use_nlp_scoring',
        },
        'pro': {
            # All detection and learning settings
            'use_llm_mapping',
            'use_learned_detector',
            'use_spacy_heuristics',
            'use_embedding_similarity',
            'use_ml_prioritization',
            'use_nlp_urgency',
            'use_nlp_scoring',
            'use_ai_page_extraction',
            'urgency_learning_scope',
            'duration_learning_scope',
            'mapping_learning_scope',
        },
        'business': {
            # Everything
            'use_llm_mapping',
            'use_learned_detector',
            'use_spacy_heuristics',
            'use_embedding_similarity',
            'use_ml_prioritization',
            'use_nlp_urgency',
            'use_rl_optimization',
            'urgency_learning_scope',
            'duration_learning_scope',
            'mapping_learning_scope',
            'slot_ranking_learning_scope',
            'use_nlp_scoring',
            'use_ai_page_extraction',
        }
    }

    # Detailed configuration for each setting
    SETTINGS_CONFIG: Dict[str, AISettingConfig] = {
        'use_llm_mapping': AISettingConfig(
            name='use_llm_mapping',
            display_name='LLM-Powered Mapping',
            description='Use advanced language models for field detection',
            tier_required='pro',
            category='detection'
        ),
        'use_learned_detector': AISettingConfig(
            name='use_learned_detector',
            display_name='Learned Field Detection',
            description='Use machine learning from your feedback',
            tier_required='pro',
            category='detection'
        ),
        'use_spacy_heuristics': AISettingConfig(
            name='use_spacy_heuristics',
            display_name='NLP Heuristics',
            description='Use natural language processing for better understanding',
            tier_required='starter',
            category='detection'
        ),
        'use_embedding_similarity': AISettingConfig(
            name='use_embedding_similarity',
            display_name='Semantic Matching',
            description='Use embeddings for semantic similarity',
            tier_required='starter',
            category='detection'
        ),
        'use_ml_prioritization': AISettingConfig(
            name='use_ml_prioritization',
            display_name='ML Task Prioritization',
            description='Machine learning-based task priority',
            tier_required='pro',
            category='optimization'
        ),
        'use_nlp_urgency': AISettingConfig(
            name='use_nlp_urgency',
            display_name='NLP Urgency Detection',
            description='Detect task urgency from text',
            tier_required='starter',
            category='detection'
        ),
        'use_rl_optimization': AISettingConfig(
            name='use_rl_optimization',
            display_name='Reinforcement Learning',
            description='Optimize scheduling with RL',
            tier_required='business',
            category='optimization'
        ),
        'urgency_learning_scope': AISettingConfig(
            name='urgency_learning_scope',
            display_name='Urgency Learning Scope',
            description='Learn urgency patterns from user/global/off',
            tier_required='pro',
            category='learning'
        ),
        'duration_learning_scope': AISettingConfig(
            name='duration_learning_scope',
            display_name='Duration Learning Scope',
            description='Learn duration patterns from user/global/off',
            tier_required='pro',
            category='learning'
        ),
        'mapping_learning_scope': AISettingConfig(
            name='mapping_learning_scope',
            display_name='Mapping Learning Scope',
            description='Learn field mappings from user/global/off',
            tier_required='pro',
            category='learning'
        ),
        'slot_ranking_learning_scope': AISettingConfig(
            name='slot_ranking_learning_scope',
            display_name='Slot Ranking Learning',
            description='Learn time slot preferences',
            tier_required='business',
            category='learning'
        ),
        'use_nlp_scoring': AISettingConfig(
            name='use_nlp_scoring',
            display_name='NLP Scoring',
            description='Score matches with NLP',
            tier_required='starter',
            category='detection'
        ),
        'use_ai_page_extraction': AISettingConfig(
            name='use_ai_page_extraction',
            display_name='AI Page Extraction',
            description='Extract tasks from Notion pages with AI',
            tier_required='pro',
            category='detection'
        ),
    }

    @classmethod
    def get_default_settings(cls) -> dict:
        """Get the default AI settings (all enabled, global learning)"""
        return {
            'use_llm_mapping': True,
            'use_learned_detector': True,
            'use_spacy_heuristics': True,
            'use_embedding_similarity': True,
            'use_ml_prioritization': True,
            'use_nlp_urgency': True,
            'use_rl_optimization': True,
            'urgency_learning_scope': 'global',
            'duration_learning_scope': 'global',
            'mapping_learning_scope': 'global',
            'slot_ranking_learning_scope': 'global',
            'use_nlp_scoring': True,
            'use_ai_page_extraction': True,
        }

    @classmethod
    def can_customize_setting(cls, tier: str, setting: str) -> bool:
        """Check if a tier can customize a specific setting"""
        if tier == 'business':
            return True  # Business can customize everything
        return setting in cls.TIER_CUSTOMIZABLE_SETTINGS.get(tier, set())

    @classmethod
    def get_tier_capabilities(cls, tier: str) -> Dict[str, bool]:
        """Get a dict of all settings and whether the tier can customize them"""
        customizable = cls.TIER_CUSTOMIZABLE_SETTINGS.get(tier, set())
        return {
            setting: setting in customizable
            for setting in cls.SETTINGS_CONFIG.keys()
        }

    @classmethod
    def get_required_tier_for_setting(cls, setting: str) -> str:
        """Get the minimum tier required to customize a setting"""
        config = cls.SETTINGS_CONFIG.get(setting)
        return config.tier_required if config else 'business'