import collections

from .downloader import Downloader, YoutubeAudioDownloader, YoutubeVideoDownloader
from .parser import Parser, YoutubeParser

PodcastType = collections.namedtuple("PodcastType", "name parser downloader")

PODCAST_TYPES = {
        "rss": PodcastType(name="RSS", parser=Parser, downloader=Downloader),
        "youtube-video": PodcastType(name="Youtube Video", parser=YoutubeParser, downloader=YoutubeVideoDownloader),
        "youtube-audio": PodcastType(name="Youtube Audio", parser=YoutubeParser, downloader=YoutubeAudioDownloader)
    }
