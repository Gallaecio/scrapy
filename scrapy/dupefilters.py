import os
import logging

from scrapy.utils.job import job_dir
from scrapy.utils.request import referer_str, RequestFingerprinter


class BaseDupeFilter:

    @classmethod
    def from_settings(cls, settings):
        return cls()

    def request_seen(self, request):
        return False

    def open(self):  # can return deferred
        pass

    def close(self, reason):  # can return a deferred
        pass

    def log(self, request, spider):  # log that a request has been filtered
        pass


class RFPDupeFilter(BaseDupeFilter):
    """Request Fingerprint duplicates filter"""

    def __init__(self, path=None, debug=False, *, fingerprinter=None):
        self.file = None
        self.fingerprinter = fingerprinter or RequestFingerprinter()
        self.fingerprints = set()
        self.logdupes = True
        self.debug = debug
        self.logger = logging.getLogger(__name__)
        if path:
            self.file = open(os.path.join(path, 'requests.seen'), 'a+')
            self.file.seek(0)
            self.fingerprints.update(x.rstrip() for x in self.file)

    @classmethod
    def from_crawler(cls, crawler):
        try:
            dupefilter = cls.from_settings(crawler.settings)
        except AttributeError:
            debug = crawler.settings.getbool('DUPEFILTER_DEBUG')
            fingerprinter = crawler.settings.getinstance(
                'REQUEST_FINGERPRINTER',
                crawler=crawler,
                singleton=True,
            )
            dupefilter = cls(
                job_dir(crawler.settings),
                debug,
                fingerprinter=fingerprinter,
            )
        return dupefilter

    @classmethod
    def from_settings(cls, settings):
        debug = settings.getbool('DUPEFILTER_DEBUG')
        fingerprinter = settings.getinstance(
            'REQUEST_FINGERPRINTER',
            singleton=True,
        )
        return cls(job_dir(settings), debug, fingerprinter=fingerprinter)

    def request_seen(self, request):
        fp = self.request_fingerprint(request)
        if fp in self.fingerprints:
            return True
        self.fingerprints.add(fp)
        if self.file:
            self.file.write(fp + '\n')

    def request_fingerprint(self, request):
        return self.fingerprinter.fingerprint(request)

    def close(self, reason):
        if self.file:
            self.file.close()

    def log(self, request, spider):
        if self.debug:
            msg = "Filtered duplicate request: %(request)s (referer: %(referer)s)"
            args = {'request': request, 'referer': referer_str(request)}
            self.logger.debug(msg, args, extra={'spider': spider})
        elif self.logdupes:
            msg = ("Filtered duplicate request: %(request)s"
                   " - no more duplicates will be shown"
                   " (see DUPEFILTER_DEBUG to show all duplicates)")
            self.logger.debug(msg, {'request': request}, extra={'spider': spider})
            self.logdupes = False

        spider.crawler.stats.inc_value('dupefilter/filtered', spider=spider)
