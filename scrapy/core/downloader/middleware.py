"""
Downloader Middleware manager

See documentation in docs/topics/downloader-middleware.rst
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any, Callable, Generator, List, Union, cast
from weakref import WeakSet, finalize

from twisted.internet.defer import Deferred, inlineCallbacks

from scrapy.exceptions import _InvalidOutput
from scrapy.http import Request, Response
from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import deferred_from_coro, mustbe_deferred

if TYPE_CHECKING:
    from twisted.python.failure import Failure

    from scrapy import Spider
    from scrapy.settings import BaseSettings


class DownloaderMiddlewareManager(MiddlewareManager):
    component_name = "downloader middleware"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.response_active_size = 0
        self._tracked_responses = WeakSet()

    @classmethod
    def _get_mwlist_from_settings(cls, settings: BaseSettings) -> List[Any]:
        return build_component_list(settings.getwithbase("DOWNLOADER_MIDDLEWARES"))

    def _add_middleware(self, mw: Any) -> None:
        if hasattr(mw, "process_request"):
            self.methods["process_request"].append(mw.process_request)
        if hasattr(mw, "process_response"):
            self.methods["process_response"].appendleft(mw.process_response)
        if hasattr(mw, "process_exception"):
            self.methods["process_exception"].appendleft(mw.process_exception)

    def _count_response_size(self, response: Response) -> None:
        if response in self._tracked_responses:
            return
        self._tracked_responses.add(response)
        size = len(response.body)
        from logging import getLogger

        logger = getLogger(__name__)
        logger.debug(
            f"{self.response_active_size=} += {size=} → {self.response_active_size + size}"
        )
        self.response_active_size += size
        finalize(response, partial(self._discount_response_size, size))

    def _discount_response_size(self, size: int) -> None:
        from logging import getLogger

        logger = getLogger(__name__)
        logger.debug(
            f"{self.response_active_size=} -= {size=} → {self.response_active_size - size}"
        )
        self.response_active_size -= size

    def download(
        self,
        download_func: Callable[[Request, Spider], Deferred[Response]],
        request: Request,
        spider: Spider,
    ) -> Deferred[Union[Response, Request]]:
        @inlineCallbacks
        def process_request(
            request: Request,
        ) -> Generator[Deferred[Any], Any, Union[Response, Request]]:
            for method in self.methods["process_request"]:
                method = cast(Callable, method)
                result = yield deferred_from_coro(
                    method(request=request, spider=spider)
                )
                if result is not None and not isinstance(result, (Response, Request)):
                    raise _InvalidOutput(
                        f"Middleware {method.__qualname__} must return None, Response or "
                        f"Request, got {result.__class__.__name__}"
                    )
                if isinstance(result, Response):
                    self._count_response_size(result)
                if result:
                    return result
            return (yield download_func(request, spider))

        @inlineCallbacks
        def process_response(
            response: Union[Response, Request]
        ) -> Generator[Deferred[Any], Any, Union[Response, Request]]:
            result = response
            if result is None:
                raise TypeError("Received None in process_response")
            elif isinstance(result, Request):
                return result

            for method in self.methods["process_response"]:
                method = cast(Callable, method)
                result = yield deferred_from_coro(
                    method(request=request, response=result, spider=spider)
                )
                if not isinstance(result, (Response, Request)):
                    raise _InvalidOutput(
                        f"Middleware {method.__qualname__} must return Response or Request, "
                        f"got {type(result)}"
                    )
                if isinstance(result, Request):
                    return result
                self._count_response_size(result)
            return result

        @inlineCallbacks
        def process_exception(
            failure: Failure,
        ) -> Generator[Deferred[Any], Any, Union[Failure, Response, Request]]:
            exception = failure.value
            for method in self.methods["process_exception"]:
                method = cast(Callable, method)
                result = yield deferred_from_coro(
                    method(request=request, exception=exception, spider=spider)
                )
                if result is not None and not isinstance(result, (Response, Request)):
                    raise _InvalidOutput(
                        f"Middleware {method.__qualname__} must return None, Response or "
                        f"Request, got {type(result)}"
                    )
                if isinstance(result, Response):
                    self._count_response_size(result)
                if result:
                    return result
            return failure

        deferred: Deferred[Union[Response, Request]] = mustbe_deferred(
            process_request, request
        )
        deferred.addErrback(process_exception)
        deferred.addCallback(process_response)
        return deferred
