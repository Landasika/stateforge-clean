from alembic import op
import sqlalchemy as sa
revision = '127be3fb000'
down_revision = '514ca0a3282c'

def upgrade():
    
    op.create_table('forumgroups',
    sa.Column('group_id', sa.Integer(), nullable=False),
    sa.Column('forum_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['forum_id'], ['forums.id'], name='fk_forum_id', use_alter=True),
    sa.ForeignKeyConstraint(['group_id'], ['groups.id'], )
    )
    


def downgrade():
    
    op.drop_table('forumgroups')
