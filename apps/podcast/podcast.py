import pickle
import yaml
from firebase_admin import firestore
from uuid import uuid4

from apps.podcast.parser import Feed

ANONYMOUS_USER_ID = None
USER_PODCAST_COLLECTION = "users-podcasts"
PODCAST_COLLECTION = "podcasts"

MAX_PODCASTS = 100
MAX_PODCAST_LINKS = 10


class PodcastParserYamlException(Exception):
    pass


class PodcastParserFormatException(Exception):
    pass


class Podcast:
    """Class represents a podcast as a name, description, and other parameters.  Becomes the
    base object for all podcasts.  Additionally, provides class and static methods for working
    with and querying for podcasts.
    """
    def __init__(self, user_uid, title, description, image, links, id=None, feed=None):
        if feed is None:
            feed = Feed(title=title, description=description, image=image, link="", entries=[])

        self.id = id
        self.user_uid = user_uid
        self.title = title
        self.description = description
        self.image = image
        self.links = links
        self.feed = feed

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
                "feed": self._feed}
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
                       feed=pickle.loads(data["feed"]))

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
    def add_user_podcasts(cls, user_uid, new_podcasts):
        db = firestore.client()
        batch = db.batch()

        user_podcasts_reference = cls._get_user_podcasts_collection(user_uid)
        user_podcasts_document = user_podcasts_reference.document()
        for podcast in new_podcasts:
            batch.set(user_podcasts_document, podcast.to_dict())

        batch.commit()

    @classmethod
    def remove_user_podcasts(cls, user_uid, podcasts):
        db = firestore.client()
        batch = db.batch()
        user_podcasts_documents = cls._get_user_podcasts_collection(user_uid).get()

        # For every existing podcast, see if it has a match in the list of podcasts.
        for document in user_podcasts_documents:
            podcast = cls.from_document(document)
            if podcast in podcasts:
                batch.delete(document.reference)
        batch.commit()

    @classmethod
    def update_user_podcasts(cls, user_uid, updated_podcasts):
        """

        :param new_podcasts:
        :return:
        """
        existing_podcasts = cls.get_user_podcasts(user_uid)
        podcasts_to_add = []
        podcasts_to_delete = []

        for old_podcast in existing_podcasts:
            if not any([old_podcast.title == p.title and
                        old_podcast.description == p.description and
                        old_podcast.links == p.links for p in updated_podcasts]):
                podcasts_to_delete.append(old_podcast)

        for new_podcast in updated_podcasts:
            if not any([new_podcast.title == p.title and
                        new_podcast.description == p.description and
                        new_podcast.links == p.links for p in existing_podcasts]):
                podcasts_to_add.append(new_podcast)

        cls.add_user_podcasts(user_uid, podcasts_to_add)
        cls.remove_user_podcasts(user_uid, podcasts_to_delete)


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


def update_user_podcasts_with_yaml(user_uid, text):
    """

    :param user_uid:
    :param text:
    :return:
    """
    podcasts = []
    # load
    try:
        pojos = yaml.load(text, Loader=yaml.SafeLoader)
    except Exception as e:
        raise PodcastParserYamlException("Invalid YAML passed to PodcastParser.")
    # empty contents
    if pojos is None:
        return podcasts

    try:
        for podcast_config in pojos:
            links = []
            for link_pojo in podcast_config["links"]:
                link = Link(url=link_pojo["url"], parser=link_pojo["parser"])
                links.append(link)

            if MAX_PODCAST_LINKS < len(links):
                raise Exception(
                    "More than max of \"{}\" podcast links provided in YAML per podcast.".format(MAX_PODCAST_LINKS))

            podcast = Podcast(user_uid=user_uid,
                              title=podcast_config["title"],
                              description=podcast_config["description"],
                              image=podcast_config["image"],
                              links=links)
            podcasts.append(podcast)
    except KeyError as e:
        raise KeyError("Missing Podcast key: {}".format(e))

    Podcast.update_user_podcasts(user_uid, podcasts)
    return podcasts


def create_user_podcasts_yaml(user_uid):
    podcasts = Podcast.get_user_podcasts(user_uid)
    podcast_pojos = []

    for podcast in podcasts:
        links = [{"url": link.url, "parser": link.parser} for link in podcast.links]
        pojo = {"title": podcast.title,
                "description": podcast.description,
                "image": podcast.image,
                "links": links}
        podcast_pojos.append(pojo)

    if 0 == len(podcast_pojos):  # since we start with an empty list
        return ""
    else:
        return yaml.dump(podcast_pojos, sort_keys=False)



