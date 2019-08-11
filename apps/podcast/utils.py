import yaml
from .parser import PARSER, get_parser_class
from .podcast import MAX_PODCAST_LINKS
from .podcast import Podcast, Feed, Link


def podcasts_from_yaml(user_uid, text):
    """

    :param user_uid:
    :param text:
    :return:
    """
    podcasts = []
    pojos = yaml.load(text, Loader=yaml.SafeLoader)

    for podcast_config in pojos:
        links = []
        for link_pojo in podcast_config["links"]:
            parser = link_pojo["parser"]
            if parser not in PARSER:
                raise ValueError("Invalid parser name")
            link = Link(url=link_pojo["url"], parser=parser)
            links.append(link)

        if MAX_PODCAST_LINKS < len(links):
            raise Exception(
                "More than max of \"{}\" podcast links provided in YAML per podcast.".format(MAX_PODCAST_LINKS))

        podcast = Podcast(user_uid=user_uid,
                          title=podcast_config["title"],
                          description=podcast_config["description"] or "",  # optional
                          image=podcast_config["image"],
                          links=links)
        podcasts.append(podcast)
    return podcasts


def yaml_from_podcasts(podcasts):
    """

    :param podcasts:
    :return:
    """
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


def get_updated_feed(podcast):
    """Utility function takes a podcast and returns a Feed

    :param podcast:
    :return:
    """
    all_entries = []
    for link in podcast.links:
        # get parser for this link
        parser_class = get_parser_class(link.parser)
        parser = parser_class()
        # parse the link feed
        feed = parser.parse_url(link.url)
        # for each entry, parse and append
        for entry in feed["entries"]:
            parsed_entry = parser.parse_entry(entry)
            if parsed_entry is not None:
                all_entries.append(parsed_entry)
    return Feed(user_uid=podcast.user_uid,
                podcast_id=podcast.id,
                entries=all_entries)
