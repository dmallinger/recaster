import datetime
import html
import pickle
from flask import request, url_for
from firebase_admin import firestore
from uuid import uuid4


RSS_HEADER_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:googleplay="http://www.google.com/schemas/play-podcasts/1.0">
<channel>
  <title>{title}</title>
  <link>{link}</link>
  <atom:link href="{link}" rel="self" type="application/rss+xml"></atom:link>
  <description>{description}</description>
  <image>
    <url>{image}</url>
    <title>{title}</title>
    <link>{link}</link>
  </image>
  <itunes:image href="{image}"></itunes:image>
  <itunes:category text="Technology">
    <itunes:category text="Podcasting"/>
  </itunes:category>
  <itunes:owner>
    <itunes:name>{title}</itunes:name>
    <itunes:email>fake@fake.com</itunes:email>
  </itunes:owner>
  <pubDate>{last_updated}</pubDate>
  <lastBuildDate>{last_updated}</lastBuildDate>
  <googleplay:block>yes</googleplay:block>
  <itunes:block>Yes</itunes:block>
  <language>en-US</language>
  """

RSS_FOOTER_TEMPLATE = """</channel>
</rss>"""

RSS_ENTRY_TEMPLATE = """
  <item>
    <title>{title}</title>
    <link>{link}</link>
    <description>{description}</description>
    <guid>{guid}</guid>
    <pubDate>{pubDate}</pubDate>
    <enclosure url="{link}" length="{bytes}" type="{mimetype}"></enclosure>
  </item>
"""

USER_PODCAST_COLLECTION = "users-podcasts"
PODCAST_COLLECTION = "podcasts"
MAX_PODCAST_LINKS = 10


class Podcast:
    """Class represents a podcast as a name, description, and other parameters.  Becomes the
    base object for all podcasts.  Additionally, provides class and static methods for working
    with and querying for podcasts.
    """
    def __init__(self, user_uid, title, description, image, links, id=None, feed=None, last_updated=None):
        self.user_uid = user_uid
        self.title = title
        self.description = description
        self.image = image
        self.links = links
        # optional params are only provided when loading from database
        self.id = id if id is not None else str(uuid4())
        self.feed = feed if feed is not None else Feed(user_uid=self.user_uid, podcast_id=self.id)
        self.last_updated = last_updated if last_updated is not None else datetime.datetime.utcnow()

    def __repr__(self):
        return "\"{}\" Podcast".format(self.title)

    def __hash__(self):
        links = tuple([(link.url, link.parser) for link in self.links])
        elements = (self.id, self.user_uid, self.title, self.description, links)
        return hash(elements)

    def __eq__(self, other):
        if not isinstance(other, Podcast):
            raise TypeError("Cannot compare Podcast with non-Podcast type.")
        return hash(self) == hash(other)

    def __ne__(self, other):
        return not (self == other)

    @property
    def links(self):
        return self._links

    @links.setter
    def links(self, links):
        self._links = sorted(links)

    @property
    def feed(self):
        return pickle.loads(self._feed)

    @feed.setter
    def feed(self, feed):
        self._feed = pickle.dumps(feed)

    def save(self):
        podcast_document = self._get_user_podcasts_collection(self.user_uid).document(self.id)
        podcast_document.set(self.to_dict())

    def to_dict(self):
        pojo = {"user_uid": self.user_uid,
                "title": self.title,
                "description": self.description,
                "image": self.image,
                "links": [link.to_dict() for link in self.links],
                "feed": self._feed,
                "last_updated": self.last_updated.timestamp()}
        return pojo

    @classmethod
    def load(cls, user_uid, podcast_id):
        document = cls._get_user_podcasts_collection(user_uid).document(podcast_id).get()
        if not document.exists:
            raise Exception("Podcast not found: {}/{}".format(user_uid, podcast_id))
        return cls.from_document(document)

    @classmethod
    def from_document(cls, document):
        data = document.to_dict()
        links = []
        for link_pojo in data["links"]:
            link = Link(url=link_pojo["url"], parser=link_pojo["parser"])
            links.append(link)
        return Podcast(id=document.id,
                       user_uid=data["user_uid"],
                       title=data["title"],
                       description=data["description"],
                       image=data["image"],
                       links=links,
                       feed=pickle.loads(data["feed"]),
                       last_updated=datetime.datetime.utcfromtimestamp(data["last_updated"]))

    @classmethod
    def _get_user_podcasts_collection(cls, user_uid):
        db = firestore.client()
        return db.collection(USER_PODCAST_COLLECTION) \
                 .document(user_uid) \
                 .collection(PODCAST_COLLECTION)

    @classmethod
    def get_user_collection(cls):
        db = firestore.client()
        return db.collection(USER_PODCAST_COLLECTION)

    @classmethod
    def get_user_podcasts(cls, user_uid):
        podcasts = []
        collection = cls._get_user_podcasts_collection(user_uid).get()
        for document in collection:
            podcasts.append(cls.from_document(document))
        return podcasts

    @classmethod
    def batch_add_user_podcasts(cls, user_uid, new_podcasts):
        db = firestore.client()
        batch = db.batch()

        user_podcasts_reference = cls._get_user_podcasts_collection(user_uid)
        for podcast in new_podcasts:
            user_podcasts_document = user_podcasts_reference.document(podcast.id)
            batch.set(user_podcasts_document, podcast.to_dict())

        batch.commit()

    @classmethod
    def batch_remove_user_podcasts(cls, user_uid, podcasts):
        db = firestore.client()
        batch = db.batch()
        user_podcasts_documents = cls._get_user_podcasts_collection(user_uid).get()

        # For every existing podcast, see if it has a match in the list of podcasts.
        for document in user_podcasts_documents:
            podcast = cls.from_document(document)
            if podcast in podcasts:
                batch.delete(document.reference)
        batch.commit()


class Link:
    def __init__(self, url, parser):
        self.url = url
        self.parser = parser

    def __hash__(self):
        return hash((self.url, self.parser))

    def __eq__(self, other):
        if not isinstance(other, Link):
            raise TypeError("Link cannot be compared with \"{}\" type.".format(type(other)))
        return self.url == other.url and self.parser == other.parser

    def __ne__(self, other):
        return not (self == other)

    def __lt__(self, other):
        return (self.url, self.parser) < (other.url, other.parser)

    def to_dict(self):
        return {"url": self.url, "parser": self.parser}

    @staticmethod
    def from_dict(link):
        return Link(url=link["url"], parser=link["parser"])


class Feed:
    def __init__(self, user_uid, podcast_id, entries=None):
        self.user_uid = user_uid
        self.podcast_id = podcast_id
        self.entries = entries if entries is not None else []
        self._sort_entries()

    def _sort_entries(self):
        self.entries = sorted(self.entries, key=lambda entry: entry.published, reverse=True)

    def add(self, entry):
        self.entries.append(entry)
        self._sort_entries()

    def to_rss(self):
        """

        :return:
        """
        # ensure updated info
        podcast = Podcast.load(self.user_uid, self.podcast_id)
        link = "{}{}".format(request.url_root[0:-1],
                             url_for("podcast", user_uid=podcast.user_uid, podcast_id=podcast.id))

        xml = RSS_HEADER_TEMPLATE.format(title=html.escape(podcast.title),
                                         description=html.escape(podcast.description),
                                         image=html.escape(podcast.image),
                                         link=html.escape(link),
                                         last_updated=podcast.last_updated.strftime("%c"))
        for entry in self.entries:
            xml = xml + entry.to_rss()

        xml = xml + RSS_FOOTER_TEMPLATE
        return xml


class FeedEntry:
    def __init__(self, parser, id, title, description, link, published):
        self.id = id
        self.parser = parser
        self.title = title
        self.description = description
        self.link = link
        self.published = published
        self.bytes = 0
        self.mimetype = None

    def __eq__(self, other):
        return self.parser == other.parser and \
               self.id == other.id

    def __ne__(self, other):
        return not (self == other)

    def to_rss(self):
        formatted_date = datetime.datetime(*self.published[:6]).strftime("%c")

        xml = RSS_ENTRY_TEMPLATE.format(guid=self.id,
                                        title=html.escape(self.title),
                                        description=html.escape(self.description),
                                        link=html.escape(self.link),
                                        pubDate=formatted_date,
                                        bytes=self.bytes,
                                        mimetype=self.mimetype)
        return xml
