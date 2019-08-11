import feedparser
import google.cloud.storage
import hashlib
import re
import urllib.parse
import urllib.request

from urllib.parse import urlparse, parse_qs
from .podcast import FeedEntry

import settings


class DownloadException(Exception):
    pass


class AbstractParser:
    NAME = None

    def parse_url(self, url):
        """Parse a URL and return a list of dictionaries representing the feed."""
        return feedparser.parse(url)

    def parse_entry(self, entry):
        """Identity function can be overwritten by inheriting classes
        to alter how entries in the RSS feed are parsed.

        :param entry: The feed entry in question
        :return: An updated dictionary representing the feed
        """
        id_ = entry["id"]
        title = entry["title"]
        description = entry["summary"]
        link = entry["link"]
        published = entry["published_parsed"]
        return FeedEntry(parser=self.NAME, id=id_, title=title,
                         description=description, link=link,
                         published=published)

    @classmethod
    def format_download(cls, content):
        """Identity function.  Can be overwritten by inheriting classes
        to reformat video files, extract audio, etc."""
        return content

    @classmethod
    def download(cls, url):
        """Downloads function at URL and then stores it publicly in our bucket.

        :param url: Location of file
        :return: The blob object of where the file is stored in Cloud Storage
        """
        storage_client = google.cloud.storage.Client()
        content, download_url, mimetype = cls._download(url)
        filename = hashlib.sha512(download_url.encode()).hexdigest()
        bucket = storage_client.get_bucket(settings.PODCAST_STORAGE_BUCKET)
        blob = bucket.blob("{}{}".format(settings.PODCAST_STORAGE_PREFIX, filename))
        blob.upload_from_string(content, mimetype)
        blob.make_public()
        return blob

    @classmethod
    def _download(cls, url):
        with urllib.request.urlopen(url) as response:
            mimetype = response.info().get_content_type()
            content = response.read()
        return content, url, mimetype


class RssParser(AbstractParser):
    NAME = "rss"


class YoutubeParser(AbstractParser):
    NAME = "youtube"
    VALID_ITAGS = None
    CHANNEL_RSS_URL_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
    VIDEO_INFO_URL_TEMPLATE = "http://youtube.com/get_video_info?video_id={}"

    def parse_url(self, url):
        with urllib.request.urlopen(url) as response:
            content = response.read().decode("utf-8")
            search_results = re.search(r'''externalId":"([^"]+)"''', content)
            if search_results is None:
                search_results = re.search(r'''channel-external-id="([^"]+)"''', content)
            if search_results is None:
                raise Exception("Couldn't find Youtube external URL")

            channel_id = search_results.groups()[0]
            rss_url = self.CHANNEL_RSS_URL_TEMPLATE.format(channel_id)
        return feedparser.parse(rss_url)

    @classmethod
    def _download(cls, url):
        video_id = parse_qs(urlparse(url).query)["v"][0]
        info_link = cls.VIDEO_INFO_URL_TEMPLATE.format(video_id)

        with urllib.request.urlopen(info_link) as response:
            content = response.read().decode("utf-8")
        query_string = parse_qs(urllib.parse.unquote(content))

        if " codecs" in query_string:
            codecs = query_string[" codecs"]
        elif "codecs" in query_string:
            codecs = query_string["codecs"]
        else:
            raise DownloadException("Could not find 'codecs' key in Youtube response!")

        for codec in codecs:
            try:
                video_url = re.search(r'''"url":"([^"]+)''', codec).groups()[0].replace("\\u0026", "&")
                mimetype = re.search(r'''"mimeType":"([^"]+)''', codec).groups()[0]
                itag = int(re.search(r'''"itag":(\d+)''', codec).groups()[0])

                if itag in cls.VALID_ITAGS:
                    with urllib.request.urlopen(video_url) as response:
                        content = response.read()
                        return content, video_url, mimetype
            except AttributeError as e:
                pass

        raise DownloadException("Could not find a valid video URL")


class YoutubeAudioParser(YoutubeParser):
    NAME = "youtube-audio"
    VALID_ITAGS = [139, 140, 141]


class YoutubeVideoParser(YoutubeParser):
    NAME = "youtube-video"
    VALID_ITAGS = [18, 22, 37]


PARSER = {
    RssParser.NAME: RssParser,
    YoutubeAudioParser.NAME: YoutubeAudioParser,
    YoutubeVideoParser.NAME: YoutubeVideoParser
}


def get_parser_class(name):
    """Return the class of the parser with this name

    :param name: name of pasrser in PARSER
    :return: parser class
    """
    return PARSER[name]

