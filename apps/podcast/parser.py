import feedparser
import google.cloud.storage
import hashlib
import re
import urllib.parse
import urllib.request
import youtube_dl

import settings


class DownloadException(Exception):
    pass


class AbstractParser:
    NAME = None

    def parse_url(self, url):
        """Parse a URL and return a list of dictionaries representing the feed."""
        return feedparser.parse(url)

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
    VALID_ITAGS = []
    CHANNEL_RSS_URL_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={}"

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
        with youtube_dl.YoutubeDL({'outtmpl': '%(id)s%(ext)s'}) as ydl:
            result = ydl.extract_info(url, download=False)

        if "entries" in result:
            # Can be a playlist or a list of videos
            video = result["entries"][0]
        else:
            # Just a video
            video = result

        try:
            file = [o for o in video["formats"] if int(o["format_id"]) in cls.VALID_ITAGS].pop(0)
        except IndexError:
            raise DownloadException("Could not find a valid video URL")
        return super(YoutubeParser, cls)._download(file["url"])


class YoutubeAudioParser(YoutubeParser):
    NAME = "youtube-audio"
    VALID_ITAGS = [139, 140, 141]


class YoutubeVideoParser(YoutubeParser):
    NAME = "youtube-video"
    VALID_ITAGS = [18, 22, 37, 43, 44, 45]


PARSERS = {
    RssParser.NAME: RssParser,
    YoutubeAudioParser.NAME: YoutubeAudioParser,
    YoutubeVideoParser.NAME: YoutubeVideoParser
}


def get_parser_class(parser):
    return PARSERS[parser]