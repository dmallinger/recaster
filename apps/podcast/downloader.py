import hashlib
import youtube_dl

import settings
from .utils import stream_upload


class DownloadException(Exception):
    pass


class Downloader:
    @classmethod
    def transform_source_url(cls, url):
        return url

    @classmethod
    def create_destination_path(cls, source_url):
        destination_name = hashlib.sha512(source_url.encode()).hexdigest()
        destination_path = f"""{settings.PODCAST_STORAGE_DIRECTORY}/{destination_name}"""
        return destination_path

    @classmethod
    def stream_download(cls, source_url, destination_path):
        return stream_upload(source_url, destination_path)

    @classmethod
    def download(cls, url):
        """Downloads function at URL and then stores it publicly in our bucket.

        :param url: Location of file
        :return: The blob object of where the file is stored in Cloud Storage
        """
        transformed_url = cls.transform_source_url(url)
        destination_path = cls.create_destination_path(transformed_url)
        blob = cls.stream_download(transformed_url, destination_path)
        blob.make_public()
        return blob


class YoutubeDownloader(Downloader):
    VALID_ITAGS = []

    @classmethod
    def transform_source_url(cls, url):
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
        return file["url"]


class YoutubeAudioDownloader(YoutubeDownloader):
    VALID_ITAGS = [139, 140, 141]


class YoutubeVideoDownloader(YoutubeDownloader):
    VALID_ITAGS = [18, 22, 37, 43, 44, 45]
