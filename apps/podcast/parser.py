import datetime
import feedparser
import ffmpeg
import google.cloud.storage
import hashlib
import html
import re
import urllib.parse
import urllib.request

from urllib.parse import urlparse, parse_qs
from uuid import uuid4

import settings

EXTERNAL_ID_REGEX1 = re.compile('''externalId":"([^"]+)"''')
EXTERNAL_ID_REGEX2 = re.compile('''channel-external-id="([^"]+)"''')
YOUTUBE_VIDEO_URL_REGEX1 = re.compile(r'''url":"([^"]*?)"''')
CHANNEL_RSS_URL_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
VIDEO_INFO_URL_TEMPLATE = "http://youtube.com/get_video_info?video_id={}"

RSS_HEADER_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
  <title>{title}</title>
  <link>{link}</link>
  <description>{description}</description>
  <image>
    <url>{image}</url>
  </image>
  """

RSS_FOOTER_TEMPLATE = """</channel>
</rss>"""

RSS_ENTRY_TEMPLATE = """
  <item>
    <title>{title}</title>
    <link>{link}</link>
    <description>{description}</description>
    <pubDate>{pubDate}</pubDate>
  </item>
"""


class DownloadException(Exception):
    pass


class Feed:
    def __init__(self, title, description, image, link, entries):
        self.title = title
        self.description = description
        self.image = image
        self.link = link
        self.entries = entries
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
        xml = RSS_HEADER_TEMPLATE.format(title=html.escape(self.title),
                                         description=html.escape(self.description),
                                         image=html.escape(self.image),
                                         link=self.link)
        for entry in self.entries:
            xml = xml + entry.to_rss()

        xml = xml + RSS_FOOTER_TEMPLATE
        return xml


class FeedEntry:
    def __init__(self, parser, title, description, link, published, downloaded=False):
        self.parser = parser
        self.title = title
        self.description = description
        self.link = link
        self.published = published
        self.downloaded = downloaded

    def __eq__(self, other):
        return self.parser == other.parser and \
               self.link == other.link and \
               self.published == other.published

    def __ne__(self, other):
        return not (self == other)

    def to_rss(self):
        formatted_date = datetime.datetime(*self.published[:6]).strftime("%c")

        xml = RSS_ENTRY_TEMPLATE.format(title=html.escape(self.title),
                                        description=html.escape(self.description),
                                        link=html.escape(self.link),
                                        pubDate=formatted_date)
        return xml


class AbstractParser:
    def parse_url(self, url):
        """Parse a URL and return a list of dictionaries representing the feed."""
        return feedparser.parse(url)

    def parse_entry(self, entry):
        """Identity function can be overwritten by inheriting classes
        to alter how entries in the RSS feed are parsed.

        :param entry: The feed entry in question
        :return: An updated dictionary representing the feed
        """
        title = entry["title"]
        description = entry["summary"]
        link = entry["link"]
        published = entry["published_parsed"]
        return FeedEntry(parser=self.NAME, title=title, description=description,
                         link=link, published=published)

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
        filename = hashlib.sha512(url.encode()).hexdigest()
        content, mimetype = cls._download(url)
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
        return content, mimetype


class RssParser(AbstractParser):
    NAME = "rss"


class YoutubeParser(AbstractParser):
    NAME = "youtube"

    def parse_url(self, url):
        with urllib.request.urlopen(url) as response:
            content = response.read().decode("utf-8")
            search_results = EXTERNAL_ID_REGEX1.search(content)
            if search_results is None:
                search_results = EXTERNAL_ID_REGEX2.search(content)
            if search_results is None:
                raise Exception("Couldn't find Youtube external URL")

            channel_id = search_results.groups()[0]
            rss_url = CHANNEL_RSS_URL_TEMPLATE.format(channel_id)
        return feedparser.parse(rss_url)

    @classmethod
    def _download(cls, url):
        video_id = parse_qs(urlparse(url).query)["v"][0]
        info_link = VIDEO_INFO_URL_TEMPLATE.format(video_id)

        with urllib.request.urlopen(info_link) as response:
            content = response.read().decode("utf-8")
        query_string = parse_qs(urllib.parse.unquote(content))

        if "player_response" in query_string:
            content = query_string["player_response"][0]
            content = content.replace("\\u0026", "&")
            video_url = YOUTUBE_VIDEO_URL_REGEX1.search(content).groups()[0]
            try:
                content, mimetype = cls._process_video(video_url)
                return content, mimetype
            except ffmpeg.Error as e:
                raise DownloadException("Could not process video URL")

        if "url" in query_string:
            # TODO: Look into this. Youtube has many (10+) urls listed for
            # some videos.  Formats are different.
            # Also, sometimes youtube returns invalid
            # codes because the video is listed as "unplayable."  Unclear
            # why these still show up in Youtube feeds.
            for video_url in query_string["url"]:
                # some mp4 videos on youtube seem to have extra information after the URL
                # that causes issues.
                video_url = video_url.split(",")[0]
                try:
                    content, mimetype = cls._process_video(video_url)
                    return content, mimetype
                except ffmpeg.Error as e:
                    raise DownloadException("Could not find video URL")
            else:
                raise DownloadException("No convertible video url found.")

        raise DownloadException("Could not find video URL")

    @classmethod
    def _process_video(cls, url):
        raise NotImplementedError("YoutubeParser is abstract and does not process videos.")


class YoutubeAudioParser(YoutubeParser):
    NAME = "youtube-audio"

    @classmethod
    def _process_video(cls, url):
        out, err = ffmpeg.input(url) \
            .audio \
            .output("pipe:", format="mp3", acodec="mp3") \
            .run(capture_stdout=True)
        return out, "audio/mpeg"


class YoutubeVideoParser(YoutubeParser):
    NAME = "youtube-video"

    @classmethod
    def _process_video(cls, url):
        # We removed processing due to audio track loss on certain files with ffmpeg.
        # Currently store/serve the raw video
        with urllib.request.urlopen(url) as response:
            content = response.read()
            mimetype = response.info().get_content_type()
            return content, mimetype


PARSER = {
    RssParser.NAME: RssParser,
    YoutubeAudioParser.NAME: YoutubeAudioParser,
    YoutubeVideoParser.NAME: YoutubeVideoParser
}


def get_parser_class(name):
    return PARSER[name]


def parse_podcast(podcast):
    all_entries = []
    for link in podcast.links:
        parser_class = get_parser_class(link.parser)
        parser = parser_class()
        feed = parser.parse_url(link.url)
        for entry in feed["entries"]:
            parsed_entry = parser.parse_entry(entry)
            if parsed_entry is not None:
                all_entries.append(parsed_entry)
    return Feed(title=podcast.title, description=podcast.description,
                image=podcast.image, link="", entries=all_entries)
