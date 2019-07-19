from flask import abort
from flask import request
from functools import wraps
from google.cloud import tasks_v2

import settings


def require_cron_job(function):
    """DECORATOR"""
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if request.headers.get("X-Appengine-Cron") == "true":
            return function(*args, **kwargs)
        else:
            abort(401)

    return decorated_function


def require_task_api_key(function):
    """DECORATOR"""
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if request.form.get("TASK_API_KEY") == settings.TASK_API_KEY:
            return function(*args, **kwargs)
        else:
            abort(401)
    return decorated_function


def add_task(relative_uri, form_data=None):
    if form_data is None:
        form_data = {}
    form_data["TASK_API_KEY"] = settings.TASK_API_KEY
    post_data = "&".join(["{}={}".format(key, value) for key, value in form_data.items()])
    client = tasks_v2.CloudTasksClient()

    parent = client.queue_path(settings.PROJECT,
                               settings.PODCAST_PARSING_QUEUE_LOCATION,
                               settings.PODCAST_PARSING_QUEUE_NAME)

    # Construct the request body.
    task = {
        'app_engine_http_request': {
            'http_method': 'POST',
            'relative_uri': relative_uri,
            'body': post_data.encode()
        }
    }
    response = client.create_task(parent, task)
    return response
