import yaml

import firebase_admin.auth
from firebase_admin import firestore

from flask import Flask
from flask import render_template
from flask import request
from flask import session

from apps.auth.utils import get_authenticated_user
from apps.auth.utils import session_login
from apps.auth.utils import required_authenticated
import settings


app = Flask(__name__)
app.secret_key = bytes(settings.SECRET_KEY, "utf-8")
firebase_app = firebase_admin.initialize_app()
db = firestore.client()


"""

{
    name:
    links: [{url: ...}, {...}, ...]
}







user_podcast
    id
    parser
    user_id
    name
    description
    url
    listing  # the rss feed in custom objects


user_metacast
    id
    user_id
    name
    description
    podcast_ids
    

podcast.yaml

- podcast:
    name: Cumtown
    description: Terrible Podcast
    link:
        - url: www.google.com
          parser: google
        - url: www.yahoo.com
          parser: microsoft


- podcast:
    name: Test 2
    description: Second Test
    link:
        - url: www.fake.com
          parser: rss

"""


@app.route('/')
def home():
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
    pass


@app.route('/podcast/<podcast_id>/')
def podcast(podcast_id):
    """Render RSS for specified podcast

    :param podcast_id: Podcast to render
    :return: RSS feed
    """
    pass

USERS_COLLECTION = "users"
USER_PODCAST_COLLECTION = "users-podcasts"
PODCAST_COLLECTION = "podcasts"

@app.route('/podcasts/')
@required_authenticated
def podcasts_list():
    podcast_yaml = """
- podcast:
    name: Cumtown
    description: Terrible Podcast
    link:
        - url: www.google.com
          parser: google
        - url: www.yahoo.com
          parser: microsoft


- podcast:
    name: Test 2
    description: Second Test
    link:
        - url: www.fake.com
          parser: rss
    """

    from apps.podcast import podcast
    x = podcast.PodcastYamlParser(podcast_yaml)
    return str(x.podcasts)

    user = get_authenticated_user()
    podcasts = db.collection(USER_PODCAST_COLLECTION).document(user.uid).collection(PODCAST_COLLECTION).get()
    print("Podcasts: {}".format(podcasts))
    return render_template("podcasts.html", podcasts=podcasts)


MAX_YAML_LENGTH = 5000

@app.route('/edit-podcasts/', methods=["GET", "POST"])
@required_authenticated
def podcasts_edit():
    user = get_authenticated_user()

    if request.method == 'POST':
        # for half-butted security, we cast the yaml to ASCII and give it a max length
        # before arbitrarily passing it to the parser.
        content = request.form["yaml"].encode("ascii", "ignore")[:MAX_YAML_LENGTH]
        try:
            podcasts = yaml.load(content)
            return "YAY!"
        except Exception:
            return render_template("podcasts_edit.html", podcast_yaml=content, yaml_error=True)
    else:
        podcasts = db.collection(USER_PODCAST_COLLECTION).document(user.uid).collection(PODCAST_COLLECTION).get()
        content = str(podcasts)
        return render_template("podcasts_edit.html", podcast_yaml=content)


@app.after_request
def add_header(response):
    response.cache_control.max_age = 300
    response.cache_control.public = True
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
