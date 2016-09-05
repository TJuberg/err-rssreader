from errbot import BotPlugin, botcmd
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
    # Holds information on feeds, for instance
    # FEEDS': {'f1016f': 'http://hnrss.org/newest?points=100'}
    'FEEDS': {},
    # Holds information on rooms/channels which are subscribed to feeds
    # 'SUBSCRIPTIONS': {'f1016f': ['#xlcteam-stage', '#databazy']}
    'SUBSCRIPTIONS': {}
}


class RSSReader(BotPlugin):
    def configure(self, configuration):
        if configuration is not None and configuration != {}:
            config = dict(chain(CONFIG_TEMPLATE.items(),
                                configuration.items()))
        else:
            config = CONFIG_TEMPLATE
        super(RSSReader, self).configure(config)

    def get_configuration_template(self):
        return CONFIG_TEMPLATE

    def check_configuration(self, configuration):
        # configuration now happens via other than the default means
        pass

    @botcmd(template='feeds')
    def rssreader_feeds(self, *args):
        """Show all feeds that are checked for updates by RSSReader."""
        return {'feeds': self.config['FEEDS']}

    @botcmd(template='subscriptions')
    def rssreader_subscriptions(self, *args):
        """Show channels which will receive new content from specific feeds."""
        subs = self.config['SUBSCRIPTIONS']
        joined_subs = {k: self.list_format(v) for k, v in subs.items()}
        return {'subscriptions': joined_subs}

    # An alias for rssreader_subscriptions
    @botcmd(template='subscriptions')
    def rssreader_subs(self, *args):
        """Show channels which will receive new content from specific feeds."""
        return self.rssreader_subscriptions(args)

    @botcmd(admin_only=True, split_args_with=None)
    def rssreader_add(self, msg, args):
        """Add URL(s) of feed(s) to be checked for updates."""
        for feed in args:
            hash = self.hash_feed(feed)
            self.config['FEEDS'][hash] = feed
            self.config['SUBSCRIPTIONS'][hash] = []

        self.save_config()
        return 'Added {}'.format(self.list_format(args))

    @botcmd(admin_only=True, split_args_with=None)
    def rssreader_rm(self, msg, args):
        """Remove feed(s) from the update loop."""
        removed = []
        for feed in args:
            if feed not in self.config['FEEDS']:
                yield 'Feed ID {} was not found'.format(feed)
                continue

            del self.config['FEEDS'][feed]
            del self.config['SUBSCRIPTIONS'][feed]
            removed.append(feed)

        self.save_config()
        if len(removed) > 0:
            yield 'Removed {}'.format(self.list_format(removed))

    @botcmd(admin_only=True, split_args_with=None)
    def rssreader_subscribe(self, msg, args):
        """Make a feed send updates to given channel(s)."""
        feed = args[0]
        if feed not in self.config['FEEDS']:
            msg_404 = 'Feed with ID {} cannot be found. Please add it first'
            return msg_404.format(feed)

        channels = args[1:]
        for channel in channels:
            self.config['SUBSCRIPTIONS'][feed].append(channel)

        self.save_config()
        return 'Subscribed {} to feed {}'.format(self.list_format(channels),
                                                 feed)

    @botcmd(admin_only=True, split_args_with=None)
    def rssreader_unsubscribe(self, msg, args):
        """Unsubscribe channels/rooms from a specific feed."""
        feed = args[0]
        if feed not in self.config['FEEDS']:
            msg_404 = 'Feed with ID {} cannot be found. Please add it first'
            return msg_404.format(feed)

        chans = args[1:]
        subs = self.config['SUBSCRIPTIONS'][feed]
        removed = []
        for channel in chans:
            try:
                subs.remove(channel)
                removed.append(channel)
            except ValueError:
                yield 'Channel {} is not subscribed to feed {}'.format(channel,
                                                                       feed)
        self.config['SUBSCRIPTIONS'][feed] = subs
        self.save_config()

        if len(removed) > 0:
            removed_formatted = self.list_format(removed)
            yield 'Unsubscribed {} from feed {}'.format(removed_formatted,
                                                        feed)

    def activate(self):
        self.shortener = Shortener('Isgd')

        self.start_poller(self.config['UPDATE_INTERVAL'], self.check_feeds)

        super(RSSReader, self).activate()

        # Make sure the hash which holds information on feeds exists when the
        # checker is ran
        try:
            if type(self['feeds']) is not dict:
                self['feeds'] = {}
        except KeyError:
            self['feeds'] = {}

    def hash_feed(self, feed_url, size=6):
        """Creates a hash ID for a feed URL."""
        return hashlib.sha224(feed_url.encode('utf-8')).hexdigest()[:size]

    def hash_entry(self, entry):
        """Creates a hash out of the feedparser's Entry. Uses just the title
        and the link as that is what we care about in most cases."""
        s = "{}{}".format(entry.title, entry.link).encode('utf-8')
        return hashlib.sha224(s).hexdigest()

    def check_feeds(self):
        """"Periodically checks for new entries in given (configured) feeds."""
        saved_feeds = self['feeds']
        for id, feed in self.config['FEEDS'].items():
            if feed not in saved_feeds:
                saved_feeds[feed] = []

            d = feedparser.parse(feed)
            past_entries = saved_feeds[feed]

            i = 1
            # Take the oldest entries first.
            for entry in reversed(d.entries):
                hash = self.hash_entry(entry)
                if hash in past_entries:
                    continue

                if i > self.config['MAX_STORIES']:
                    break

                self.sender(d, entry, id)
                i += 1
                past_entries.insert(0, hash)
            saved_feeds[feed] = past_entries[:self.config['ENTRY_CACHE_SIZE']]
        self['feeds'] = saved_feeds
        return ''

    def sender(self, d, entry, feed_id):
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

        for channel in self.config['SUBSCRIPTIONS'][feed_id]:
            identifier = self.build_identifier(channel)
            self.send(identifier, s)

    def list_format(self, list):
        n = len(list)
        if n > 1:
            return ('{}, ' * (len(list) - 2) + '{} and {}').format(*list)
        elif n > 0:
            return list[0]
        else:
            return ''

    def save_config(self):
        """Save edited configuration to Errbot's internal structures."""

        return self._bot.plugin_manager.set_plugin_configuration('RSSReader',
                                                                 self.config)
