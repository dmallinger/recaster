# Recaster

## Overview
Recaster is a web platform designed to convert media into podcasts.  For example (and the current primary use case) converting Youtube channels into podcasts.  The benefit is that one can now use a podcast app to automatically download videos as they come out, watch offline, and resume playing.

There are two driving forces for Recaster:
1. Create podcasts from non-traditional sources (e.g. Youtube).
1. Do so in a manner that is cheap as possible.

## Recaster and Google Cloud
Recaster runs on Google Cloud.  It is designed to run as cheaply as possible via architectural decisions that fit it into the free tier of Cloud.  For example, as of time of this writing, the system runs with eight podcasts for pennies / week.

Components of the system that are explicitly Google Cloud include:

- Database: Podcast and feed data are stored in Firestore.
- Cloud Storage: The podcast files are stored in Google's Cloud Storage.  This makes files unaffected by any throttling or URL changes by third parties like Youtube.
- Tasks: Downloads and podcast feed updates are done asynchronously via Tasks.

## How to install and run
This instruction set is incomplete.  It should be enough for someone familiar with Google Cloud or willing to work through their permission and configuration documentation.  Over time, we will update this to be a full tutorial for programmers new to Google Cloud.
1. Create a new Google Cloud Project
    1. Select Firestore Native Mode
    1. Select your region
    1. Enable billing for this project
1. Create a new Firebase project
    1. Link it to your App Engine project
    1. Enable User Sign-In methods
1. Review and follow the quick starts here: https://cloud.google.com/sdk/docs/quickstarts
1. Install requirements via `pip install -r requirements.txt`
1. Go to Cloud Scheduler and create a new schedule with the following parameters:
    - Name: start-parsing
    - Description: "Queues up all users for podcast parsing"
    - Frequency: */30 * * * *
    - Target: App Engine HTTP
    - URL: /internal/start-parsing/
1. Create a Cloud Task Queue by following the instructions here: https://cloud.google.com/tasks/docs/quickstart-appengine
    1. Enable the Task queue API
    1. Create a task queue via `gcloud tasks queues create [QUEUE_ID]`
1. Download the JSON credential file
    1. Go to "IAM & Admin" > "Service Accounts"
    1. Download the firebase key
    1. Save this somewhere safe!
    1. Set the environment variable `export GOOGLE_APPLICATION_CREDENTIALS=<your path>`
1. Create `settings.py`
    1. Copy `settings.py.example` into `settings.py`
    1. `PROJECT` is the name of your Google project
    1. `SECRET_KEY` should be a random string (do NOT share it)
    1. `PODCAST_PARSING_QUEUE_NAME` is the name of your Google Task queue
    1. `PODCAST_PARSING_QUEUE_LOCATION` is the geo location of the Task queue 
    1. `PODCAST_STORAGE_BUCKET` is the bucket where these podcast episodes will be saved
    1. `TASK_API_KEY` should be a random string (do NOT share it)
1. Run `gcloud app deploy` to push your new Recaster project into the cloud!

## How to contribute
Contact me on github and we'll figure it out!