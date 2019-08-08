import traceback
import sys
import yaml

import firebase_admin.auth
from firebase_admin import firestore

from flask import abort
from flask import Flask
from flask import render_template
from flask import redirect
from flask import request
from flask import Response
from flask import session
from flask import url_for
from functools import wraps

from apps.auth.utils import is_authenticated, get_authenticated_user
from apps.auth.utils import session_login, session_logout
from apps.auth.utils import require_authenticated
from apps.podcast import Podcast
from apps.podcast.podcast import update_user_podcasts_with_yaml, create_user_podcasts_yaml
from apps.podcast.parser import parse_podcast, get_parser_class, DownloadException
from apps.tasks import require_cron_job, require_task_api_key
from apps.tasks import add_task, get_task_arguments
import settings

OK_RESPONSE = "Ok"

app = Flask(__name__)
app.secret_key = bytes(settings.SECRET_KEY, "utf-8")
firebase_app = firebase_admin.initialize_app()
db = firestore.client()


@app.route('/')
def home():
    """Homepage"""
    return render_template("home.html")


@app.route('/login/')
def login():
    """Login page"""
    return render_template("login.html")


@app.route('/authenticate/', methods=["POST"])
def authenticate():
    """Called by the browser after the return status from FirebaseUI login

    :return: The user_id (to be received by the browser).
    """
    token = request.form["token"]
    decoded_token = firebase_admin.auth.verify_id_token(token)
    user_uid = decoded_token['uid']
    user = firebase_admin.auth.get_user(user_uid)
    session_login(user)
    return user_uid


@app.route('/logout/')
def logout():
    """Logs user out of current session and then redirects home"""
    session_logout()
    return redirect(url_for("home"))


@app.route('/podcast/<user_uid>/<podcast_id>/')
def podcast(user_uid, podcast_id):
    """Render RSS for specified podcast

    :param podcast_id: Podcast to render
    :return: RSS feed
    """
    podcast = Podcast.load(user_uid, podcast_id)
    return Response(podcast.feed.to_rss(), mimetype="text/xml")


@app.route('/podcasts/')
@require_authenticated
def podcasts_list():
    """View all podcasts for this user.

    :return: the template of all podcasts for this user. rendered to view.
    """
    user = get_authenticated_user()
    podcasts = Podcast.get_user_podcasts(user.uid)

    return render_template("podcasts.html", podcasts=podcasts)


@app.route('/edit-podcasts/', methods=["GET", "POST"])
@require_authenticated
def podcasts_edit():
    """Allow a user to edit their list of podcasts as a YAML file

    :return: Renders the template of podcasts initially and redirects to
             podcast_list upon successful update.
    """
    user = get_authenticated_user()
    if request.method == 'POST':
        content = request.form["yaml"]
        try:
            update_user_podcasts_with_yaml(user.uid, content)
            return redirect(url_for("podcasts_list"))
        except Exception as e:
            content = create_user_podcasts_yaml(user.uid)
            tb = traceback.format_exc()
            return render_template("podcasts_edit.html", podcast_yaml=content, traceback=tb, yaml_error=True)
    else:
        content = create_user_podcasts_yaml(user.uid)
        return render_template("podcasts_edit.html", podcast_yaml=content)


@app.route('/internal/start-parsing', methods=["GET", "POST"])
@require_cron_job
def task_start_parsing():
    """Cron job starts parsing.  Calls tasks as these can (depending on
    configuration) run for longer than ordinary crons and web calls.

    :return: Ok
    """
    add_task(url_for("task_queue_users"))
    return OK_RESPONSE


@app.route('/internal/queue-users', methods=["GET", "POST"])
@require_task_api_key
def task_queue_users():
    """Second step in parsing.  Gets all users and makes a task
    for each one to parse their updated podcasts.

    :return: Ok
    """
    users = firebase_admin.auth.list_users().iterate_all()
    for user in users:
        if user.disabled:  # skip disabled users
            continue
        # add user task
        add_task(url_for("task_queue_podcasts"), {"user_uid": user.uid})

    return OK_RESPONSE


@app.route('/internal/queue-podcasts', methods=["GET", "POST"])
@require_task_api_key
def task_queue_podcasts():
    """Third step in parsing.  Massively parallelize by making a separate
    task for each podcast when parsing.

    :return: Ok
    """
    data = get_task_arguments()
    user_uid = data["user_uid"]

    podcasts = Podcast.get_user_podcasts(user_uid)
    for podcast in podcasts:
        add_task(url_for("task_parse_podcast"), {"user_uid": user_uid,
                                                 "podcast_id": podcast.id})
    return OK_RESPONSE


@app.route('/internal/parse-podcast', methods=["GET", "POST"])
@require_task_api_key
def task_parse_podcast():
    """Fourth step in parsing.  Parse the feed text and queue tasks
    for downloading/converting content.

    :return: Ok
    """
    data = get_task_arguments()
    user_uid = data["user_uid"]
    podcast_id = data["podcast_id"]

    podcast = Podcast.load(user_uid, podcast_id)
    feed = podcast.feed  # performance. prevents pickling behind the scenes
    new_feed = parse_podcast(podcast)

    for entry in new_feed.entries:
        if any([entry.parser == e.parser and
                entry.title == e.title and
                entry.published == e.published for e in feed.entries]):
            continue
        feed.add(entry)
    podcast.feed = feed
    podcast.save()
    add_task(url_for("task_recursive_download_podcast"),
             {"user_uid": user_uid, "podcast_id": podcast_id})
    return OK_RESPONSE


@app.route('/internal/download-podcast', methods=["GET", "POST"])
@require_task_api_key
def task_recursive_download_podcast():
    """Fifth and last step in parsing.  Download the content and save it.
    We make this recursive because the free tier of App Engine limits the
    length of time a process can run for.  This will (hopefully) allow us
    to download a greater number of files without running over time limits.
    :return: Ok
    """
    data = get_task_arguments()
    user_uid = data["user_uid"]
    podcast_id = data["podcast_id"]

    podcast = Podcast.load(user_uid, podcast_id)
    feed = podcast.feed  # performance: prevents behind-the-scenes repeat pickling

    # THIS IS NOT A FOR LOOP
    # this loop iterates over entries but breaks after it finds the first one
    # needing downloading.  This is done to (severely) limit the runtime of the
    # script as the app engine free tier limits task runtime.
    for entry in feed.entries:
        if entry.downloaded:
            continue
        else:
            # use the parser to download content
            # NOTE: this is where parsers like youtube-audio do their
            # conversions.
            parser_class = get_parser_class(entry.parser)
            parser = parser_class()

            try:
                blob = parser.download(entry.link)
                # update the entry to have our location and new
                entry.link = blob.public_url
            except DownloadException:
                # no ability to download, so keep the original URL and move on.
                pass

            entry.downloaded = True
            # update feed and save (recall feed has pointers to the updated entry)
            podcast.feed = feed
            podcast.save()
            # call this task again.  this ensures the system (serially) downloads
            # all the content for this URL
            add_task(url_for("task_recursive_download_podcast"),
                     {"user_uid": user_uid, "podcast_id": podcast_id})
            break
    return OK_RESPONSE


@app.context_processor
def inject_dict_for_all_templates():
    """Adds variables to the templates for all templates.

    :return: A dictionary of variables
    """
    global_vars = {}

    if is_authenticated():
        global_vars["user"] = get_authenticated_user()

    return global_vars


@app.after_request
def add_header(response):
    """Alter the response object to include no-cache headers.

    :param response: The response object for the view being rendered
    :return: an updated response object
    """
    response.cache_control.public = True
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.errorhandler(401)
def unauthorized_access_handler(e):
    """Render unauthorized access

    :param e: error object
    :return: Template for the 401 page.
    """
    return render_template("401.html")


if __name__ == '__main__':
    # This is used when running locally only. When deploying to Google App
    # Engine, a webserver process such as Gunicorn will serve the app. This
    # can be configured by adding an `entrypoint` to app.yaml.
    # Flask's development server will automatically serve static files in
    # the "static" directory. See:
    # http://flask.pocoo.org/docs/1.0/quickstart/#static-files. Once deployed,
    # App Engine itself will serve those files as configured in app.yaml.
    app.run(host='127.0.0.1', port=8080, debug=True)
