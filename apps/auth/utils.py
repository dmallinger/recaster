"""

"""

from flask import abort
from flask import session
from functools import wraps

USER_KEY = "user_uid"


def login(user):
    """assumes user was authenticated!"""
    session[USER_KEY] = user.uid
    session.permanent = True  # keep session after browser closer


def is_authenticated():
    return USER_KEY in session


def required_authenticated(function):
    """DECORATOR"""
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if is_authenticated():
            return function(*args, **kwargs)
        else:
            abort(401)
    return decorated_function

