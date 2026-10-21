import os
from flaskbb import create_app
from flaskbb.utils.helpers import ReverseProxyPathFix

_basepath = os.path.dirname(os.path.abspath(__file__))

flaskbb = create_app(config='flaskbb.cfg')

