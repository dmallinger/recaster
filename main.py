import firebase_admin.auth

from flask import Flask
from flask import make_response
from flask import render_template
from flask import request

from apps.auth.utils import required_authenticated

app = Flask(__name__)
firebase_app = firebase_admin.initialize_app()


@app.route('/')
def home():
    return render_template("login.html")


@app.route('/authenticate/', methods=["POST"])
def authenticate():
    token = request.form["token"]
    decoded_token = firebase_admin.auth.verify_id_token(token)
    user_uid = decoded_token['uid']
    user = f(user_uid)
    login(user)
    return uid


@app.route('/podcast/')
@required_authenticated
def podcast_add():
    return "Hello world, I'm {}".format(podcast_id)


@app.route('/podcast/<podcast_id>')
@required_authenticated
def podcast_edit(podcast_id):
    return "Hello world, I'm {}".format(podcast_id)


@app.route('/podcasts/<user_id>')
def podcast_list(user_id):
    dummy_times = [cookie for cookie in request.cookies]
    text = str(dir(request))
    html = render_template('login.html', times=dummy_times, text=text)
    response = make_response(html)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return str(dir(firebase_admin.auth))

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
