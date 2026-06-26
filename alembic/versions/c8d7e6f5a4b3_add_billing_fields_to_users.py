"""add billing fields to users

Revision ID: c8d7e6f5a4b3
Revises: 9522d151504e
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c8d7e6f5a4b3'
down_revision: Union[str, Sequence[str], None] = '9522d151504e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('plan', sa.String(10), nullable=True))
    op.add_column('users', sa.Column('stripe_customer_id', sa.String(64), nullable=True))
    op.add_column('users', sa.Column('stripe_subscription_id', sa.String(64), nullable=True))
    op.add_column('users', sa.Column('billing_currency', sa.String(3), nullable=True))
    op.add_column('users', sa.Column('billing_period_end', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('sessions_used_this_month', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('billing_month', sa.Date(), nullable=True))

    op.create_index('ix_users_stripe_subscription_id', 'users', ['stripe_subscription_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_users_stripe_subscription_id', table_name='users')
    op.drop_column('users', 'billing_month')
    op.drop_column('users', 'sessions_used_this_month')
    op.drop_column('users', 'cancel_at_period_end')
    op.drop_column('users', 'billing_period_end')
    op.drop_column('users', 'billing_currency')
    op.drop_column('users', 'stripe_subscription_id')
    op.drop_column('users', 'stripe_customer_id')
    op.drop_column('users', 'plan')
