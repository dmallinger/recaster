import yaml

import firebase_admin.auth
from firebase_admin import firestore

from flask import Flask
from flask import render_template
from flask import redirect
from flask import request
from flask import session
from flask import url_for

from apps.auth.utils import is_authenticated, get_authenticated_user
from apps.auth.utils import session_login, session_logout
from apps.auth.utils import required_authenticated
from apps.podcast import Podcast
import settings


app = Flask(__name__)
app.secret_key = bytes(settings.SECRET_KEY, "utf-8")
firebase_app = firebase_admin.initialize_app()
db = firestore.client()


@app.route('/')
def home():
    return render_template("home.html")


@app.route('/login/')
def login():
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
    session_logout()
    return redirect(url_for("home"))


@app.route('/podcast/<podcast_id>/')
def podcast(podcast_id):
    """Render RSS for specified podcast

    :param podcast_id: Podcast to render
    :return: RSS feed
    """
    pass


@app.route('/podcasts/')
@required_authenticated
def podcasts_list():
    user = get_authenticated_user()
    podcasts = Podcast.get_user_podcasts(user.uid)

    return render_template("podcasts.html", podcasts=podcasts)


@app.route('/edit-podcasts/', methods=["GET", "POST"])
@required_authenticated
def podcasts_edit():

    from apps.podcast.podcast import Podcast
    import traceback

    user = get_authenticated_user()


    print(dir(user))

    if request.method == 'POST':
        content = request.form["yaml"]
        try:
            podcasts = Podcast.parse_user_podcasts_yaml(content)
            Podcast.save_user_podcasts(user.uid, podcasts)
            return redirect(url_for("podcasts_list"))
        except Exception as e:
            tb = traceback.format_exc()
            return render_template("podcasts_edit.html", podcast_yaml=tb, yaml_error=True)
    else:
        content = Podcast.get_user_podcasts_yaml(user.uid)
        return render_template("podcasts_edit.html", podcast_yaml=content)


@app.context_processor
def inject_dict_for_all_templates():
    global_vars = {}

    if is_authenticated():
        global_vars["user"] = get_authenticated_user()

    return global_vars


@app.after_request
def add_header(response):
    response.cache_control.public = True
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.errorhandler(401)
def unauthorized_access_handler(e):
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
