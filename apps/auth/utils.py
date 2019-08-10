import firebase_admin.auth

from firebase_admin import firestore
from flask import abort
from flask import session
from functools import wraps

USER_KEY = "USER"


def session_login(user):
    """Login user.  Assumes user was authenticated!
    :param user: the Firebase user
    :return: None
    """
    session[USER_KEY] = user.uid
    session.permanent = True  # keep session after browser closer


def session_logout():
    """Logout current user from session."""
    del session[USER_KEY]


def is_authenticated():
    """Does the current session have a user?"""
    if USER_KEY in session:
        user = get_authenticated_user()
        if user is not None and not user.disabled:
            return True
    return False


def get_authenticated_user():
    """Get the currently logged in user.

    :return: Firebase user object"""
    db = firestore.client()

    if USER_KEY not in session:
        raise Exception("No active session")
    else:
        try:
            user_uid = session[USER_KEY]
            user = firebase_admin.auth.get_user(user_uid)
            return user
        except firebase_admin.auth.AuthError as e:
            return None


def require_authenticated(function):
    """DECORATOR function.  Enforces that the current session has an
    authenticated user. Otherwise, aborts.

    :param function: The view to be wrapped
    :return: Decorated function
    """
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if is_authenticated():
            return function(*args, **kwargs)
        else:
            abort(401)
    return decorated_function

