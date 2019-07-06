import yaml


class PodcastParserYamlException(Exception):
    pass


class PodcastParserFormatException(Exception):
    pass


class PodcastYamlParser:
    def __init__(self, podcast_yaml):
        podcasts = []

        try:
            contents = yaml.load(podcast_yaml, Loader=yaml.SafeLoader)
        except Exception as e:
            raise PodcastParserYamlException("Invalid YAML passed to PodcastParser.")

        try:
            for podcast_config in contents:
                name = podcast_config["podcast"]["name"]
                description = podcast_config["podcast"]["name"]
                for link in podcast_config["podcast"]["link"]:
                    url = link["url"]
                    parser = link["parser"]
                    podcast = Podcast(name=name, description=description, url=url, parser=parser)
                    podcasts.append(podcast)
        except KeyError as e:
            raise KeyError("Missing Podcast key: {}".format(e))

        self.podcast_yaml = podcast_yaml
        self.podcasts = [str(o) for o in podcasts]


class Podcast:
    def __init__(self, name, description, url, parser):
        """

        :param name:
        :param description:
        :param url:
        :param parser:
        """
        self.name = name
        self.description = description
        self.url = url
        self.parser = parser

    def __str__(self):
        return "\"{}\" Podcast at \"{}\"".format(self.name, self.url)

class Episode:
    pass


