import feedparser


class Parser:
    @classmethod
    def get_parser(cls, name):
        return PARSER[name]

    def parse_podcast(self, podcast):
        all_entries = []
        for link in podcast.links:
            parser = feedparser
            feed = parser.parse(link.url)
            all_entries.extend(feed["entries"])
        sorted_entries = sorted(all_entries, key=lambda entry: entry["published_parsed"], reverse=True)
        return {
                "name": podcast.name,
                "description": podcast.description,
                "entries": sorted_entries
            }

    def parse_rss(self, url):
        return feedparser.parse(url)

    def parse(self, url):
        raise NotImplementedError("Parser.parse is an abstract method")


class RssParser(Parser):
    def parse(self, url):
        return self.parse_rss(url)


PARSER = {
    "rss": RssParser
}

