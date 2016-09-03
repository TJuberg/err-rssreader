from errbot import BotPlugin
from pyshorteners import Shortener
import feedparser
import hashlib
from itertools import chain

CONFIG_TEMPLATE = {
    'MSG_FORMAT': '{0} > {1} > {2}',
    'MAX_STORIES': 5,
    'UPDATE_INTERVAL': 30,
    'MAX_LINK_LENGTH': 50,
    'ENTRY_CACHE_SIZE': 100,
    'FEEDS': [],
    'CHANNELS': []
}


class RSSPlugin(BotPlugin):
    def configure(self, configuration):
        print(configuration)
        if configuration is not None and configuration != {}:
            config = dict(chain(CONFIG_TEMPLATE.items(),
                                configuration.items()))
        else:
            config = CONFIG_TEMPLATE

        print(config)
        super(RSSPlugin, self).configure(config)

    def get_configuration_template(self):
        return CONFIG_TEMPLATE

    def check_configuration(self, configuration):
        # TODO: This is a nasty hack which makes the plugin actually
        # configurable. In the future we aim to make the standard way of
        # configuring this plugin obsolete (yes, even the errbot's core devs
        # suggest this as the best way of providing a reasonable configuration
        # option).
        pass

    def activate(self):
        self.shortener = Shortener('Isgd')

        self.start_poller(self.config['UPDATE_INTERVAL'], self.check_feeds)

        super(RSSPlugin, self).activate()

        # Make sure the hash which holds information on feeds exists when the
        # checker is ran
        try:
            if type(self['feeds']) is not dict:
                self['feeds'] = {}
        except KeyError:
            self['feeds'] = {}

    def hash_entry(self, entry):
        """Creates a hash out of the feedparser's Entry. Uses just the title
        and the link as that is what we care about in most cases."""
        s = "{}{}".format(entry.title, entry.link).encode('utf-8')
        return hashlib.sha224(s).hexdigest()

    def check_feeds(self):
        """"Periodically checks for new entries in given (configured) feeds."""
        saved_feeds = self['feeds']
        for feed in self.config['FEEDS']:
            if feed not in saved_feeds:
                saved_feeds[feed] = []
        self['feeds'] = saved_feeds

        for feed in self.config['FEEDS']:
            d = feedparser.parse(feed)
            past_entries = self['feeds'][feed]

            i = 1
            for entry in d.entries:
                hash = self.hash_entry(entry)
                if hash in past_entries:
                    continue

                if i > self.config['MAX_STORIES']:
                    break

                self.sender(d, entry)
                i += 1
                past_entries.insert(0, hash)
            saved_feeds[feed] = past_entries[:self.config['ENTRY_CACHE_SIZE']]
        self['feeds'] = saved_feeds
        return ''

    def sender(self, d, entry):
        """A helper function that takes care of sending the entry that we
        regard as 'new' to proper places. Moreover, it takes care of formatting
        the raw entry into textual representation and shortening the entry
        link if it is too long."""
        link = entry.link
        if len(link) > self.config['MAX_LINK_LENGTH']:
            link = self.shortener.short(link)

        s = self.config['MSG_FORMAT'].format(d.feed.title,
                                             entry.title,
                                             link)

        for channel in self.config['CHANNELS']:
            identifier = self.build_identifier(channel)
            self.send(identifier, s)
