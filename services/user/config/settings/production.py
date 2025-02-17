from .base import *

# set allowed host when debug false
hosts = env.str("DJANGO_ALLOWED_HOSTS","").split(",")
ALLOWED_HOSTS = hosts