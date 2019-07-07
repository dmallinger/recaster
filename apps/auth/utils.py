import firebase_admin.auth

from firebase_admin import firestore
from flask import abort
from flask import session
from functools import wraps

USER_KEY = "USER"


def session_login(user):
    """assumes user was authenticated!"""
    session[USER_KEY] = user.uid
    session.permanent = True  # keep session after browser closer


def session_logout():
    del session[USER_KEY]


def is_authenticated():
    return USER_KEY in session


def get_authenticated_user():
    db = firestore.client()

    if not is_authenticated():
        raise Exception("No activate session")
    else:
        user_uid = session[USER_KEY]
        user = firebase_admin.auth.get_user(user_uid)
        return user


def required_authenticated(function):
    """DECORATOR"""
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if is_authenticated():
            return function(*args, **kwargs)
        else:
            abort(401)
    return decorated_function

