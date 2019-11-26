import feedparser
import re
import urllib.parse
import urllib.request


class Parser:
    """
    any instantiations MUST conform to the feedparser structure in returning parsed data
    """
    def parse_url(self, url):
        """Parse a URL and return a list of dictionaries representing the feed."""
        return feedparser.parse(url)


class YoutubeParser(Parser):
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

            search_results = re.search(r'''<meta property="og:image" content="([^"]+)"''', content)
            image_url = search_results.groups()[0]
        feed = feedparser.parse(rss_url)
        feed["feed"]["description"] = f"""Channel for {feed["feed"]["author"]}"""
        feed["feed"]["image"] = {"href": image_url}
        return feed
