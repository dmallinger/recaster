import datetime
import feedparser
import ffmpeg
import google.cloud.storage
import hashlib
import html
import re
import urllib.parse
import urllib.request

from flask import url_for, request
from urllib.parse import urlparse, parse_qs
from uuid import uuid4

import settings

EXTERNAL_ID_REGEX1 = re.compile('''externalId":"([^"]+)"''')
EXTERNAL_ID_REGEX2 = re.compile('''channel-external-id="([^"]+)"''')
YOUTUBE_VIDEO_URL_REGEX1 = re.compile(r'''url":"([^"]*?)"''')
CHANNEL_RSS_URL_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
VIDEO_INFO_URL_TEMPLATE = "http://youtube.com/get_video_info?video_id={}"

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


class DownloadException(Exception):
    pass


class Feed:
    def __init__(self, podcast, entries=None):
        self.podcast = podcast
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
        # HACK! handles an import issue until we:
        # TODO: refactor to move Parser in podcast.py
        #  and then make this Podcast.load(self.user_uid, self.podcast_id)
        # ensure updated info in our pickled podcast
        podcast = self.podcast.load(self.podcast.user_uid, self.podcast.id)
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


def parse_podcast(podcast):
    """Utility function takes a podcast and returns a Feed

    :param podcast:
    :return:
    """
    all_entries = []
    for link in podcast.links:
        parser_class = get_parser_class(link.parser)
        parser = parser_class()
        feed = parser.parse_url(link.url)
        for entry in feed["entries"]:
            parsed_entry = parser.parse_entry(entry)
            if parsed_entry is not None:
                all_entries.append(parsed_entry)
    return Feed(podcast=podcast,
                entries=all_entries)
