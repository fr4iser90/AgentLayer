"""Allow non-LLM model default policy profiles."""

from alembic import op


revision = "schema_106"
down_revision = "schema_105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE model_default_policies
          DROP CONSTRAINT IF EXISTS model_default_policies_profile_check;
        ALTER TABLE model_default_policies
          ADD CONSTRAINT model_default_policies_profile_check
          CHECK (profile IN ('default', 'agent', 'coding', 'vlm', 'embedding', 'extractor', 'stt', 'tts'));
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM model_default_policies
        WHERE profile IN ('embedding', 'extractor', 'stt', 'tts');
        ALTER TABLE model_default_policies
          DROP CONSTRAINT IF EXISTS model_default_policies_profile_check;
        ALTER TABLE model_default_policies
          ADD CONSTRAINT model_default_policies_profile_check
          CHECK (profile IN ('default', 'agent', 'coding', 'vlm'));
        """
    )
