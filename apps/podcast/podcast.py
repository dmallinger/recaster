import yaml
from firebase_admin import firestore

"""
podcast (unique by (user_id, url, parser))
    id
    user_id
    name
    description
    links
    listing  # the rss feed in custom objects

episode (unique by (podcast, parser)
    id
    podcast_uid
    parser
    content
    
    
    
- name: Cumtown
  description: Disgusting
  links:
    - url: google.com
      parser: rss
    - url: yahoo.com
      parser: old

- podcast
    - name: 

"""

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
    def __init__(self, name, description, url=None, parser=None, links=None):
        """

        :param name:
        :param description:
        :param url:
        :param parser:
        """
        if links is None and url is None:
            raise Exception("Podcast must be initialized with either a URL or a links object.")

        if links is not None and url is not None:
            raise Exception("Cannot provide both links and url to Podcast.")

        self.name = name
        self.description = description

        if links is not None:
            self.links = links
        else:
            self.links = [Link(url=url, parser=parser)]

    @property
    def links(self):
        return self._links

    @links.setter
    def links(self, links):
        self._links = sorted(links)

    def __repr__(self):
        return "\"{}\" Podcast".format(self.name)

    def __hash__(self):
        return hash(self.get_link_tuples())

    def __eq__(self, other):
        if not isinstance(other, Podcast):
            raise TypeError("Cannot compare Podcast with non-Podcast type.")

        # Links are kept in a sorted form to make comparisons fast
        return self.name == other.name and self.links == other.links

    def __ne__(self, other):
        return not (self == other)

    def __cmp__(self, other):
        raise NotImplementedError("Podcast does not support ordered comparison, only equality.")

    def get_link_tuples(self):
        return [(link.url, link.parser) for link in self.links]

    def to_dict(self):
        pojo = {"name": self.name,
                "description": self.description,
                "links": [link.to_dict() for link in self.links]}
        return pojo

    @classmethod
    def get_user_podcasts_reference(cls, user_uid):
        db = firestore.client()
        return db.collection(USER_PODCAST_COLLECTION) \
                 .document(user_uid) \
                 .collection(PODCAST_COLLECTION)

    @classmethod
    def get_user_podcasts_documents(cls, user_uid):
        reference = cls.get_user_podcasts_reference(user_uid)
        return reference.get()

    @classmethod
    def get_user_podcasts(cls, user_uid):
        return (Podcast.from_dict(o.to_dict()) for o in cls.get_user_podcasts_documents(user_uid))

    @classmethod
    def save_user_podcasts(cls, user_uid, new_podcasts):
        """

        :param new_podcasts:
        :return:
        """
        db = firestore.client()

        if len(new_podcasts) > MAX_PODCASTS:
            raise Exception("Users cannot have more than {} podcasts.".format(MAX_PODCASTS))

        batch = db.batch()

        user_podcasts_documents = cls.get_user_podcasts_documents(user_uid)
        matched_podcasts = []

        # For every existing podcast, see if it has a match in the new list of podcasts.
        # If no match exists, delete it.  If a match exists, note that.  We'll look for all the
        # podcasts that didn't have a match later so that we can add them.
        for document in user_podcasts_documents:
            podcast = Podcast.from_dict(document.to_dict())
            if podcast not in new_podcasts:
                batch.delete(document.reference)
            else:
                matched_podcasts.append(podcast)

        # Add all the podcasts that didn't have a match.
        user_podcasts_reference = cls.get_user_podcasts_reference(user_uid)
        for podcast in new_podcasts:
            if podcast not in matched_podcasts:
                document = user_podcasts_reference.document()
                batch.set(document, podcast.to_dict())

        batch.commit()

    @classmethod
    def parse_user_podcasts_yaml(cls, text):
        podcasts = []

        try:
            pojos = yaml.load(text, Loader=yaml.SafeLoader)
        except Exception as e:
            raise PodcastParserYamlException("Invalid YAML passed to PodcastParser.")

        if pojos is None:  # empty contents
            return podcasts

        try:
            for podcast_config in pojos:
                podcast = Podcast.from_dict(podcast_config)

                if MAX_PODCAST_LINKS < len(podcast.links):
                    raise Exception(
                        "More than max of \"{}\" podcast links provided in YAML per podcast.".format(MAX_PODCAST_LINKS))

                podcasts.append(podcast)
        except KeyError as e:
            raise KeyError("Missing Podcast key: {}".format(e))

        return podcasts

    @classmethod
    def get_user_podcasts_yaml(cls, user_uid):
        """Given a user_uid, returns their podcast configuration in dynamic yaml.

        :param user_uid: User in question
        :return: The string yaml contents representing said user's podcast configuration.
        """
        podcasts = cls.get_user_podcasts(user_uid)
        podcast_pojos = [o.to_dict() for o in podcasts]

        if 0 == len(podcast_pojos):  # since we start with an empty list
            return ""
        else:
            return yaml.dump(podcast_pojos, sort_keys=False)

    @staticmethod
    def from_dict(dict_):
        links = []
        for link in dict_["links"]:
            links.append(Link.from_dict(link))

        return Podcast(name=dict_["name"],
                       description=dict_["description"],
                       links=links)


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

    # def __cmp__(self, other):
    #     return cmp((self.url, self.parser), (other.url, other.parser))

    def to_dict(self):
        return {"url": self.url, "parser": self.parser}

    @staticmethod
    def from_dict(link):
        return Link(url=link["url"], parser=link["parser"])


class Episode:
    pass


