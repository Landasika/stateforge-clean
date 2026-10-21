from alembic import op
import sqlalchemy as sa
revision = '221d918aa9f0'
down_revision = '127be3fb000'

def upgrade():
    
    
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('activated', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('last_failed_login', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('login_attempts', sa.Integer(), nullable=True))

def downgrade():
    
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('activated')
        batch_op.drop_column('login_attempts')
        batch_op.drop_column('last_failed_login')
    
