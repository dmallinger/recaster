import datetime
import email.utils
import urllib.request
from flask import request, url_for, render_template
from firebase_admin import firestore
from uuid import uuid4
from .type import PODCAST_TYPES


USER_PODCAST_COLLECTION = "users-podcasts"
PODCAST_COLLECTION = "podcasts"


class PodcastParserException(Exception):
    pass


class Podcast:
    """Class represents a podcast as a name, description, and other parameters.  Becomes the
    base object for all podcasts.  Additionally, provides class and static methods for working
    with and querying for podcasts.
    """
    def __init__(self, user_uid, podcast_type, url):
        self.id = None
        self.feed = None
        self.user_uid = user_uid
        self.podcast_type = podcast_type
        self.url = url
        self.last_accessed = None

    def initialize(self):
        parser = PODCAST_TYPES[self.podcast_type].parser()
        try:
            if self.id is None:
                self.id = str(uuid4())
            feed = parser.parse_url(self.url)
            self.feed = Feed(user_uid=self.user_uid,
                             podcast_id=self.id,
                             title=feed["feed"]["title"],
                             description=feed["feed"]["description"],
                             image_url=feed["feed"]["image"]["href"],
                             last_updated=datetime.datetime.utcnow())
            self.last_accessed = datetime.datetime.utcnow()
        except Exception:
            raise PodcastParserException(f"""Could not parse podcast ({self.url}, {self.podcast_type})""")

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return self.id == other.id

    def __ne__(self, other):
        return not (self == other)

    def delete(self):
        podcast_document = self.get_user_podcasts_collection(self.user_uid).document(self.id)
        return podcast_document.delete()

    def save(self):
        podcast_document = self.get_user_podcasts_collection(self.user_uid).document(self.id)
        return podcast_document.set(self.to_dict())

    def to_dict(self):
        pojo = {"id": self.id,
                "user_uid": self.user_uid,
                "podcast_type": self.podcast_type,
                "url": self.url,
                "feed": self.feed.to_dict(),
                "last_accessed": self.last_accessed.timestamp()}
        return pojo

    def load_feed(self):
        all_entries = []
        podcast_type = PODCAST_TYPES[self.podcast_type]
        parser = podcast_type.parser()
        # parse the link feed
        feed = parser.parse_url(self.url)
        # for each entry, parse and append
        for entry in feed["entries"]:
            link_info = urllib.request.urlopen(entry["link"]).info()
            bytes_ = link_info.get("Content-Length", 0)
            content_type = link_info.get("Content-Type", "")
            feed_entry = FeedEntry(id=entry["id"],
                                   title=entry["title"],
                                   description=entry["description"],
                                   link=entry["link"],
                                   published=datetime.datetime(*(entry["published_parsed"][:6])),
                                   bytes=bytes_,
                                   mimetype=content_type)
            all_entries.append(feed_entry)
        return Feed(user_uid=self.user_uid,
                    podcast_id=self.id,
                    title=feed["feed"]["title"],
                    description=feed["feed"]["description"],
                    image_url=feed["feed"]["image"]["href"],
                    last_updated=datetime.datetime.utcnow(),
                    entries=all_entries)

    @classmethod
    def load(cls, user_uid, podcast_id):
        document = cls.get_user_podcasts_collection(user_uid).document(podcast_id).get()
        if not document.exists:
            raise Exception(f"""Podcast not found: {user_uid}/{podcast_id}""")
        return cls.from_document(document)

    @classmethod
    def from_dict(cls, dict_):
        podcast = Podcast(user_uid=dict_["user_uid"],
                          podcast_type=dict_["podcast_type"],
                          url=dict_["url"])
        podcast.id = dict_["id"]
        podcast.feed = Feed.from_dict(dict_["feed"])
        podcast.last_accessed = datetime.datetime.fromtimestamp(dict_["last_accessed"])
        return podcast

    @classmethod
    def from_document(cls, document):
        return cls.from_dict(document.to_dict())

    @classmethod
    def get_user_collection(cls):
        db = firestore.client()
        return db.collection(USER_PODCAST_COLLECTION)

    @classmethod
    def get_user_podcasts_collection(cls, user_uid):
        return cls.get_user_collection() \
                  .document(user_uid) \
                  .collection(PODCAST_COLLECTION)

    @classmethod
    def get_user_podcasts(cls, user_uid):
        podcasts = []
        collection = cls.get_user_podcasts_collection(user_uid).get()
        for document in collection:
            podcasts.append(cls.from_document(document.reference.get()))
        return podcasts

    @classmethod
    def batch_add_user_podcasts(cls, user_uid, new_podcasts):
        db = firestore.client()
        batch = db.batch()

        user_podcasts_reference = cls.get_user_podcasts_collection(user_uid)
        for podcast in new_podcasts:
            user_podcasts_document = user_podcasts_reference.document(podcast.id)
            batch.set(user_podcasts_document, podcast.to_dict())

        batch.commit()

    @classmethod
    def batch_remove_user_podcasts(cls, user_uid, podcasts):
        db = firestore.client()
        batch = db.batch()
        user_podcasts_documents = cls.get_user_podcasts_collection(user_uid).get()

        # For every existing podcast, see if it has a match in the list of podcasts.
        for document in user_podcasts_documents:
            podcast = cls.from_document(document)
            if podcast in podcasts:
                batch.delete(document.reference)
        batch.commit()


class Feed:
    def __init__(self, title, description,
                 image_url, last_updated, entries=None,
                 user_uid=None, podcast_id=None, link=None):

        self.title = title
        self.description = description
        self.image_url = image_url
        self.last_updated = last_updated
        self.entries = entries if entries is not None else []
        self._sort_entries()

        if user_uid is None and podcast_id is None and link is not None:
            self.link = link

        elif user_uid is not None and podcast_id is not None and link is None:
            self.link = "{}{}".format(request.url_root[0:-1],
                                      url_for("podcast", user_uid=user_uid, podcast_id=podcast_id))
        else:
            raise Exception("Specify one (only one) of (user_uid, podcast_id) or (link)")

    def _sort_entries(self):
        self.entries = sorted(self.entries, key=lambda entry: entry.published, reverse=True)

    def insert(self, entry):
        self.entries.append(entry)
        self._sort_entries()

    def remove(self, entry):
        self.entries = [e for e in self.entries if entry != e]

    def to_dict(self):
        return {"link": self.link,
                "title": self.title,
                "description": self.description,
                "image_url": self.image_url,
                "last_updated": self.last_updated.timestamp(),
                "entries": [entry.to_dict() for entry in self.entries]}

    def to_rss(self):
        return render_template("podcast.rss",
                               title=self.title,
                               description=self.description,
                               image=self.image_url,
                               link=self.link,
                               last_updated=email.utils.format_datetime(self.last_updated),
                               entries=self.entries)

    @classmethod
    def from_dict(cls, feed_dict):
        return Feed(link=feed_dict["link"],
                    title=feed_dict["title"],
                    description=feed_dict["description"],
                    image_url=feed_dict["image_url"],
                    last_updated=datetime.datetime.fromtimestamp(feed_dict["last_updated"]),
                    entries=[FeedEntry.from_dict(e) for e in feed_dict["entries"]])


class FeedEntry:
    def __init__(self, id, title, description, link, published, bytes, mimetype):
        self.id = id
        self.title = title
        self.description = description
        self.link = link
        self.published = published
        self.bytes = bytes
        self.mimetype = mimetype

    def __eq__(self, other):
        return self.id == other.id

    def __ne__(self, other):
        return not (self == other)

    @property
    def published_formatted(self):
        return email.utils.format_datetime(self.published)

    def to_dict(self):
        return {"id": self.id,
                "title": self.title,
                "description": self.description,
                "link": self.link,
                "published": self.published.timestamp(),
                "bytes": self.bytes,
                "mimetype": self.mimetype}

    @classmethod
    def from_dict(cls, feed_entry_dict):
        return FeedEntry(id=feed_entry_dict["id"],
                         title=feed_entry_dict["title"],
                         description=feed_entry_dict["description"],
                         link=feed_entry_dict["link"],
                         published=datetime.datetime.fromtimestamp(feed_entry_dict["published"]),
                         bytes=feed_entry_dict["bytes"],
                         mimetype=feed_entry_dict["mimetype"])
