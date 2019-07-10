from google.cloud import tasks_v2


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
