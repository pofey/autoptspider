import asyncio
import logging
import time
from enum import Enum
from multiprocessing import Queue, Process
from typing import Union, List, Dict, Optional

from httpcore import TimeoutException
from tenacity import stop_after_delay, wait_exponential, retry_if_not_exception_type, AsyncRetrying

from moviebotapi.site import SiteUserinfo

from autoptspider.site.basesitehelper import BaseSiteHelper
from autoptspider.site.exceptions import RequestOverloadException, LoginRequired
from autoptspider.site.sitebuilder import SiteBuilder

_LOGGER = logging.getLogger(__name__)


class SiteSearcher:
    run_time = None
    interval_secs = 10

    def __init__(self,
                 site_helper: BaseSiteHelper,
                 query=None,
                 cate_level1_list: list = None,
                 network_error_retry=False,
                 timeout: int = None,
                 search_value_type: Union[None, List] = None,
                 all_pages: bool = False,
                 error_waiting_time: int = 600
                 ):
        self.site_helper = site_helper
        self.querys = []
        if query:
            for q in query:
                if search_value_type and q.get('value_type') and q.get('value_type') not in search_value_type:
                    continue
                self.querys.append(q)
        self.network_error_retry = network_error_retry
        self.cate_level1_list = cate_level1_list
        self.timeout = timeout
        self.all_pages = all_pages
        self.cur_page = 0
        if not error_waiting_time:
            self.error_waiting_time = 600
        else:
            self.error_waiting_time = error_waiting_time

    def get_run_time(self):
        return round(self.run_time, 2) if self.run_time else 0

    def get_site_helper(self):
        return self.site_helper

    def get_site_id(self):
        return self.site_helper.get_id()

    def get_site_name(self):
        return self.site_helper.get_name()

    def get_query_str(self):
        return [i.get('value') for i in self.querys]

    async def _search(self, q, params):
        res = []
        ids = set()
        while True:
            try:
                if self.cur_page:
                    params.update({'page': self.cur_page})
                r = await self.site_helper.search(**params)
                if not self.all_pages:
                    res = r
                    break
                if not r:
                    break
                if r[0].id in ids:
                    # 避免站点适配文件有bug，发现重复就停止
                    _LOGGER.error(
                        f"{self.get_site_name()}搜索{q.get('value')} 第{self.cur_page}页 发现重复内容，结束翻页")
                    break
                self.cur_page += 1
                res += r
                if self.cur_page > 10:
                    _LOGGER.info(f"{self.get_site_name()}搜索{q.get('value')} 搜索结果超过10页，停止自动翻页")
                    break
                for t in r:
                    ids.add(t.id)
                await asyncio.sleep(1)
            except RequestOverloadException as e:
                await asyncio.sleep(e.stop_secs)
                raise e
        return res

    async def search(self):
        start = time.perf_counter()
        try:
            ids: set = set()
            res = []
            for i, q in enumerate(self.querys):
                params = {
                    q.get('key'): q.get('value'),
                    'cate_level1_list': self.cate_level1_list,
                    'timeout': self.timeout
                }
                if self.network_error_retry:
                    async for attempt in AsyncRetrying(retry=retry_if_not_exception_type(LoginRequired),
                                                       stop=stop_after_delay(self.error_waiting_time),
                                                       wait=wait_exponential(multiplier=1, min=5, max=120)):
                        with attempt:
                            r = await self._search(q, params)
                else:
                    r = await self._search(q, params)
                if not r:
                    continue
                for t in r:
                    if t.id in ids:
                        continue
                    res.append(t)
                    ids.add(t.id)
                if i + 1 < len(self.querys):
                    await asyncio.sleep(self.interval_secs)
            self.cur_page = 0
            return {'code': 0, 'data': res}
        except LoginRequired as e:
            raise e
        finally:
            end = time.perf_counter()
            self.run_time = end - start

    async def list(self):
        start = time.perf_counter()
        try:
            if self.network_error_retry:
                async for attempt in AsyncRetrying(retry=retry_if_not_exception_type(LoginRequired),
                                                   stop=stop_after_delay(600),
                                                   wait=wait_exponential(multiplier=1, min=20, max=120)):
                    with attempt:
                        try:
                            r = await self.site_helper.list(10, self.cate_level1_list)
                        except RequestOverloadException as e:
                            await asyncio.sleep(e.stop_secs)
                            raise e
                        except Exception as e:
                            _LOGGER.info(f"{self.get_site_name()}获取最新种子列表出错，自动重试中，错误信息：{repr(e)}")
                            raise e
            else:
                r = await self.site_helper.list(10, self.cate_level1_list)
            return r
        except LoginRequired as e:
            raise e
        finally:
            end = time.perf_counter()
            self.run_time = end - start

    async def get_userinfo(self, refresh: bool = False) -> Optional[SiteUserinfo]:
        start = time.perf_counter()
        try:
            if self.network_error_retry:
                async for attempt in AsyncRetrying(retry=retry_if_not_exception_type(LoginRequired),
                                                   stop=stop_after_delay(600),
                                                   wait=wait_exponential(multiplier=1, min=20, max=120)):
                    with attempt:
                        try:
                            r = await self.site_helper.get_userinfo(refresh)
                        except RequestOverloadException as e:
                            await asyncio.sleep(e.stop_secs)
                            raise e
                        except Exception as e:
                            _LOGGER.info(f"{self.get_site_name()}获取最新用户信息出错，自动重试中，错误信息：{repr(e)}")
                            raise e
            else:
                r = await self.site_helper.get_userinfo(refresh)
            return r
        except LoginRequired as e:
            raise e
        finally:
            end = time.perf_counter()
            self.run_time = end - start


class ResultType(str, Enum):
    AllFinished = 'AllFinished'
    Timeout = 'Timeout'
    LoginError = 'LoginError'
    Error = 'Error'
    Result = 'Result'


class SiteInvokerResult:
    site_id: str
    site_name: str
    query_str: str
    runtime: float
    err_msg: Optional[str]
    data: Union[None, List, SiteUserinfo]

    def __init__(self, site_id: str, site_name: str, query_str: str, runtime: float, err_msg: Optional[str] = None,
                 data: Union[None, List, SiteUserinfo] = None):
        self.site_id = site_id
        self.site_name = site_name
        self.query_str = query_str
        self.runtime = runtime
        self.err_msg = err_msg
        self.data = data


class ResultMessage:
    result_type: ResultType
    data: SiteInvokerResult

    def __init__(self, result_type: ResultType, data: SiteInvokerResult = None):
        self.result_type = result_type
        self.data = data


class SiteInvokerFunction(str, Enum):
    Search = '_search'
    List = '_list'
    GetUser = '_get_user'


class _MultiSearcherInvoker:
    def __init__(self, searcher_config: List[Dict], q: Queue,
                 method: Union[SiteInvokerFunction, List[SiteInvokerFunction]]):
        self.searcher_config = searcher_config
        self.q = q
        if isinstance(method, SiteInvokerFunction):
            method = [method]
        self.method: List[SiteInvokerFunction] = method

    @staticmethod
    def _build_searcher(searcher_config) -> List[SiteSearcher]:
        if not searcher_config:
            return []
        searchers: List[SiteSearcher] = []
        for config in searcher_config:
            site = config.get('site')
            s = SiteSearcher(
                SiteBuilder.build(
                    site.get('site_config'),
                    site.get('cookie'),
                    site.get('proxies'),
                    site.get('user_agent'),
                ),
                config.get('query'),
                config.get('cate_level1_list'),
                config.get('network_error_retry'),
                config.get('timeout'),
                search_value_type=config.get('search_value_type'),
                all_pages=config.get('all_pages'),
                error_waiting_time=config.get('error_waiting_time'),
            )
            searchers.append(s)
        return searchers

    def __call__(self):
        for name in self.method:
            m = getattr(self, name.value)
            m()
        self.q.put(ResultMessage(ResultType.AllFinished))

    @staticmethod
    def _build_result(searcher: SiteSearcher, e: Optional[Exception] = None,
                      data: Union[None, List, SiteUserinfo] = None):
        return SiteInvokerResult(
            site_id=searcher.get_site_id(),
            site_name=searcher.get_site_name(),
            query_str=str(searcher.get_query_str()) if searcher.get_query_str() else None,
            runtime=float(searcher.get_run_time()) if searcher.get_run_time() else 0,
            err_msg=str(e) if e else None,
            data=data
        )

    def _process(self, searchers: Dict[object, SiteSearcher], tasks: List):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        finished, unfinished = loop.run_until_complete(asyncio.wait(tasks))
        for task in finished:
            searcher = searchers.get(task.get_coro())
            try:
                res = task.result()
            except LoginRequired as e:
                self.q.put(ResultMessage(ResultType.LoginError, self._build_result(searcher, e)))
                continue
            except TimeoutException as e:
                self.q.put(ResultMessage(ResultType.Timeout, self._build_result(searcher, e)))
                continue
            except Exception as e:
                self.q.put(ResultMessage(ResultType.Error, self._build_result(searcher, e)))
                continue
            if not res:
                continue
            if isinstance(res, dict) and res.get('code') == 1:
                self.q.put(ResultMessage(ResultType.Timeout, self._build_result(searcher)))
                continue
            self.q.put(
                ResultMessage(ResultType.Result, self._build_result(searcher,
                                                                    data=res.get('data') if res and isinstance(res,
                                                                                                               dict) else res)))

        if unfinished:
            for task in unfinished:
                searcher = searchers.get(task.get_coro())
                self.q.put(ResultMessage(ResultType.Timeout, self._build_result(searcher)))

    def _list(self):
        searcher = self._build_searcher(self.searcher_config)
        if not searcher:
            self.q.put(ResultMessage(ResultType.AllFinished))
            return []
        tasks = []
        searchers: Dict[object, SiteSearcher] = dict()
        for s in searcher:
            t = s.list()
            tasks.append(t)
            searchers[t] = s
        self._process(searchers, tasks)

    def _search(self):
        searcher = self._build_searcher(self.searcher_config)
        if not searcher:
            self.q.put(ResultMessage(ResultType.AllFinished))
            return []
        tasks = []
        searchers: Dict[object, SiteSearcher] = dict()
        for s in searcher:
            t = s.search()
            tasks.append(t)
            searchers[t] = s
        self._process(searchers, tasks)

    def _get_user(self):
        searcher = self._build_searcher(self.searcher_config)
        if not searcher:
            self.q.put(ResultMessage(ResultType.AllFinished))
            return []
        tasks = []
        searchers: Dict[object, SiteSearcher] = dict()
        for s in searcher:
            t = s.get_userinfo()
            tasks.append(t)
            searchers[t] = s
        self._process(searchers, tasks)


class MultiSiteProcess:
    def __init__(self, searchers: List[Dict], q: Queue,
                 functions: Union[SiteInvokerFunction, List[SiteInvokerFunction]]):
        self.process = Process(target=_MultiSearcherInvoker(searchers, q, functions),
                               name='MultiSearchProcess')

    def __enter__(self):
        self.process.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.process.terminate()
