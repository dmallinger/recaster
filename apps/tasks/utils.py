from flask import abort
from flask import request
from functools import wraps
from google.cloud import tasks_v2
from urllib.parse import parse_qs

import settings


def get_task_arguments():
    """Tasks are sent with binary encoding (required) and Flask doesn't seem
    to parse that into request.form. So we use this function to get the
    parameters sent.
    Note that all parameters parse to lists.  So:
        request.form.get("username")
        becomes:
        get_task_arguments()["username"][0]

    :return: A dict of arguments to this task.
    """
    data = parse_qs(request.data.decode("utf-8"))
    for key in data:
        data[key] = data[key][0]
    data.update(request.args)
    data.update(request.form)
    return data


def require_cron_job(function):
    """DECORATOR function.  Only allow function to be run by
    App Engine cron.

    :param function: The view to be run as a cron job.
    :return: The decorated function
    """
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if request.headers.get("X-Appengine-Cron") == "true":
            return function(*args, **kwargs)
        else:
            abort(401)

    return decorated_function


def require_task_api_key(function):
    """DECORATOR function.  Determines if the task API key is including
    via POST data.  If not, aborts.

    :param function: the view function being decorated
    :return: The decorated function
    """
    @wraps(function)
    def decorated_function(*args, **kwargs):
        data = get_task_arguments()
        api_key = data["TASK_API_KEY"][0]
        if api_key == settings.TASK_API_KEY:
            return function(*args, **kwargs)
        else:
            abort(401)
    return decorated_function


def add_task(relative_uri, form_data=None):
    """Submits a task for execution.  Includes a task API key by default
    for security.  This key must be checked for by the task being run!

    :param relative_uri: Task URI
    :param form_data: Data to be passed to task
    :return: Task response object
    """
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
