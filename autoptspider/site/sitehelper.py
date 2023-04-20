import asyncio
import logging
import random
import re
from http.cookies import SimpleCookie
from typing import List, Optional, Dict

import aiofiles
import httpx
from httpx import Timeout
from jinja2 import Template
from pyquery import PyQuery
from pyrate_limiter import Limiter, RequestRate, Duration
from tenacity import retry, stop_after_delay, wait_exponential, wait_fixed, stop_after_attempt, \
    retry_if_not_exception_type

from moviebotapi.site import SiteUserinfo, TorrentList, CateLevel1, TorrentDetail

from autoptspider.site.basesitehelper import BaseSiteHelper
from autoptspider.site.exceptions import LoginRequired, RequestOverloadException
from autoptspider.site.siteexceptions import RateLimitException
from autoptspider.site.siteparser import SiteParser
from autoptspider.utils.numberutils import NumberUtils

download_limiter = Limiter(RequestRate(1, 15 * Duration.SECOND))

_LOGGER = logging.getLogger(__name__)
ALL_CATE_LEVEL1 = [CateLevel1.Movie,
                   CateLevel1.TV,
                   CateLevel1.Documentary,
                   CateLevel1.Anime,
                   CateLevel1.Music,
                   CateLevel1.AV,
                   CateLevel1.Game,
                   CateLevel1.Other]


class SiteHelper(BaseSiteHelper):
    headers = {
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36'}
    cookies = None
    last_search_text: Optional[str] = None
    userinfo = None

    def __init__(self, site_config, cookie_str=None, request_timeout=10.0, download_timeout=180.0, proxies=None,
                 user_agent=None):
        self.request_timeout = request_timeout
        self.download_timeout = download_timeout
        self.cookie_str = cookie_str
        self.set_cookie(cookie_str)
        self.site_config = site_config
        self.category_mappings = self._init_category_mappings(site_config.get('category_mappings'))
        self.search_paths = self._init_search_paths(site_config.get('search').get('paths'), self.category_mappings)
        self.search_query = self._init_search_query(site_config.get('search').get('query'))
        if proxies:
            self.proxies = proxies
        else:
            self.proxies = None
        if user_agent:
            self.headers['user-agent'] = user_agent
        self.user_agent = self.headers['user-agent']
        self._pre_init_template(self.site_config)

    @staticmethod
    def _pre_init_template(site_config):
        if not site_config:
            return
        SiteHelper._pre_init_template_by_fields(site_config.get('torrents', {}).get('fields'))
        SiteHelper._pre_init_template_by_fields(site_config.get('list', {}).get('fields'))

    @staticmethod
    def _pre_init_template_by_fields(fields):
        if not fields:
            return
        if fields:
            for key in fields:
                rule = fields[key]
                if 'text' in rule:
                    if isinstance(rule['text'], str) and rule['text'].find('{') != -1:
                        rule['_template'] = Template(rule['text'])
                if 'default_value' in rule:
                    if isinstance(rule['default_value'], str) and rule['default_value'].find('{') != -1:
                        rule['_default_value_template'] = Template(rule['default_value'])

    def set_cookie(self, cookie_str: str):
        if not cookie_str:
            return
        cookie = SimpleCookie(cookie_str)
        cookies = {}
        for key, morsel in cookie.items():
            cookies[key] = morsel.value
        self.cookies = cookies

    def _update_cookies(self, r):
        if not r or not self.cookies:
            return
        if r.cookies:
            for k in r.cookies:
                self.cookies[k] = r.cookies[k]

    def _render_querystring(self, query):
        qs = ''
        for key in self.search_query:
            val = self.search_query[key]
            if isinstance(val, Template):
                val = val.render({'query': query})
            if key == '$raw' and val is not None and val != '':
                qs += val
            elif val is not None and val != '':
                qs += f'{key}={val}&'
        if qs:
            qs = qs.rstrip('&')
        return qs

    @staticmethod
    def _init_search_paths(paths_config, category_mappings):
        paths = []
        for p in paths_config:
            obj: dict = dict()
            obj['path'] = p.get('path')
            cate_ids_config = p.get('categories')
            search_cate_ids = []
            if cate_ids_config:
                # 如果可用id第一个字符为!，则说明是排除设置模式
                if cate_ids_config[0] == '!':
                    for c in category_mappings:
                        if (int(c['id']) if c['id'] else 0) not in cate_ids_config:
                            search_cate_ids.append(str(c['id']))
                else:
                    search_cate_ids = [str(c) for c in cate_ids_config]
            else:
                search_cate_ids = [str(c['id']) for c in category_mappings]
            obj['categories'] = search_cate_ids
            if p.get('method'):
                obj['method'] = p.get('method')
            else:
                obj['method'] = 'get'
            paths.append(obj)
        return paths

    @staticmethod
    def _init_search_query(query_config):
        query_tmpl = {}
        for key in query_config:
            val = query_config[key]
            if isinstance(val, str) and val.find('{') != -1:
                query_tmpl[key] = Template(val)
            else:
                query_tmpl[key] = val
        return query_tmpl

    async def _pass_cloudflare(self, res):
        text = res.text
        if text.find('data-cf-settings') != -1 and text.find('rocket-loader') != -1:
            # 基本的水墙，解析js后再跳转访问即可
            match_js_var = re.search(r'window.location=(.+);', res.text)
            if match_js_var:
                check_uri = eval(match_js_var.group(1))
                async with httpx.AsyncClient(
                        headers=self.headers,
                        cookies=self.cookies,
                        follow_redirects=True,
                        timeout=Timeout(timeout=self.request_timeout),
                        proxies=self.proxies,
                        verify=False
                ) as client:
                    return await client.get(self.get_domain() + check_uri)
        elif res.status_code == 503 and text.find('<title>Just a moment...</title>') != -1:
            # 高级版水墙，需要模拟浏览器登陆跳过
            _LOGGER.error(f'{self.get_name()}检测到CloudFlare 5秒盾，请浏览器访问跳过拿到新Cookie重新配置。')
            raise LoginRequired(self.get_id(), self.get_name(),
                                f'{self.get_name()}检测到CloudFlare 5秒盾，登陆失败，请浏览器访问重新获取Cookie！')
        return res

    async def _check_and_get_response(self, res):
        res = await self._pass_cloudflare(res)
        text = res.text
        if text.find('负载过高，120秒后自动刷新') != -1:
            raise RequestOverloadException('负载过高，120秒后自动刷新', self.get_id(), self.get_name(), 120)
        self._update_cookies(res)
        return res

    @retry(retry=retry_if_not_exception_type(LoginRequired), stop=stop_after_delay(600),
           wait=wait_exponential(multiplier=1, min=30, max=120))
    async def get_userinfo_page_text(self):
        url = self.site_config.get('userinfo').get('path')
        if not url:
            return
        async with httpx.AsyncClient(
                headers=self.headers,
                cookies=self.cookies,
                http2=False,
                timeout=Timeout(timeout=self.request_timeout),
                proxies=self.proxies,
                follow_redirects=True,
                verify=False
        ) as client:
            r = await self._check_and_get_response(await client.get(url))
            return self._get_response_text(r)

    @staticmethod
    def trans_to_userinfo(result: dict):
        user = SiteUserinfo()
        user.uid = int(result['uid'])
        user.username = result['username']
        user.user_group = result['user_group']
        user.uploaded = NumberUtils.trans_size_str_to_mb(str(result['uploaded']))
        user.downloaded = NumberUtils.trans_size_str_to_mb(str(result['downloaded']))
        try:
            user.seeding = int(result['seeding'])
        except Exception as e:
            user.seeding = 0
        try:
            user.leeching = int(result['leeching'])
        except Exception as e:
            user.leeching = 0
        try:
            if 'share_ratio' in result:
                ss = result['share_ratio'].replace(',', '')
                user.share_ratio = float(ss)
            else:
                if not user.downloaded:
                    user.share_ratio = float('inf')
                else:
                    user.share_ratio = round(user.uploaded / user.downloaded, 2)
        except Exception as e:
            user.share_ratio = 0.0
        user.vip_group = result['vip_group']
        return user

    async def get_userinfo(self, refresh=False) -> SiteUserinfo:
        if not refresh and self.last_search_text:
            # 用上次搜索结果页内容做解析
            text = self.last_search_text
        else:
            text = await self.get_userinfo_page_text()
        with SiteParser(self.site_config, PyQuery(text) if text else None) as parser:
            res = parser.parse_userinfo()
        self.userinfo = res
        return self.trans_to_userinfo(res)

    async def list(self, timeout=None, cate_level1_list=None) -> TorrentList:
        if not timeout:
            timeout = self.request_timeout
        list_parser = self.site_config.get('list')
        if list_parser:
            headers = self.headers
            headers['Referer'] = self.get_domain()
            async with httpx.AsyncClient(
                    headers=headers,
                    cookies=self.cookies,
                    timeout=timeout,
                    proxies=self.proxies,
                    follow_redirects=True,
                    verify=False
            ) as client:
                url = f'{self.get_domain()}{list_parser.get("path")}'
                r = await self._check_and_get_response(await client.get(url))
                text = self._get_response_text(r)
                if not text:
                    return []
                self.last_search_text = text
                with SiteParser(self.site_config, PyQuery(text), list_parser) as parser:
                    if not self.userinfo:
                        self.userinfo = parser.parse_userinfo()
                    search_result = parser.parse_torrents(context={'userinfo': self.userinfo})
            return search_result
        else:
            return await self.search(cate_level1_list=cate_level1_list if cate_level1_list else ALL_CATE_LEVEL1,
                                     timeout=timeout)

    def _build_search_path(self, cate_level1_list: Optional[List[CateLevel1]]) -> List[Dict]:
        if not cate_level1_list:
            return []
        input_cate2_ids = set(self.__get_cate_level2_ids__(cate_level1_list))
        paths = []
        # 根据传入一级分类数据，查找真正要执行的搜索path，一级对应分类
        for p in self.search_paths:
            cpath = p.copy()
            cate_in = list(set(cpath['categories']).intersection(input_cate2_ids))
            if not cate_in:
                continue
            del cpath['categories']
            if len(cate_in) == len(self.category_mappings):
                # 如果等于全部，不需要传分类
                cpath['query_cates'] = []
            else:
                cpath['query_cates'] = cate_in
            paths.append(cpath)
        return paths

    async def search(
            self,
            keyword=None,
            imdb_id=None,
            cate_level1_list: Optional[List[CateLevel1]] = None,
            free: bool = False,
            page: Optional[int] = None,
            timeout=None
    ) -> TorrentList:
        if not self.search_paths:
            return []
        paths = self._build_search_path(cate_level1_list)
        if not paths:
            # 配置文件的分类设置有问题或者真的不存在此分类
            return []
        query = {}
        if keyword:
            query['keyword'] = keyword
        if imdb_id:
            query['imdb_id'] = imdb_id
        if free:
            query['free'] = free
        else:
            query['cates'] = []
        if page:
            query['page'] = page
        search_result: TorrentList = []
        if not timeout:
            timeout = self.request_timeout
        for i, p in enumerate(paths):
            if p.get('query_cates'):
                query['cates'] = self._trans_search_cate_id(p.get('query_cates'))
            uri = p.get('path')
            qs = self._render_querystring(query)
            headers = self.headers
            headers['Referer'] = f'{self.get_domain()}{uri}'
            async with httpx.AsyncClient(
                    headers=headers,
                    cookies=self.cookies,
                    timeout=timeout,
                    proxies=self.proxies,
                    follow_redirects=True,
                    verify=False
            ) as client:
                if p.get('method') == 'get':
                    url = f'{self.get_domain()}{uri}?{qs}'
                    r = await client.get(url)
                else:
                    url = f'{self.get_domain()}{uri}'
                    r = await client.post(url, data=qs)
                text = self._get_response_text(await self._check_and_get_response(r))
                if not text:
                    continue
                self.last_search_text = text
                with SiteParser(self.site_config, PyQuery(text)) as parser:
                    if not self.userinfo:
                        self.userinfo = parser.parse_userinfo()
                    torrents = parser.parse_torrents(context={'userinfo': self.userinfo})
                if torrents:
                    search_result += torrents
            if i + 1 < len(paths):
                # 多页面搜索随机延迟
                await asyncio.sleep(random.randint(1, 3))
        return search_result

    def __check_limit__(self, text, err_msg):
        if not text:
            return
        if text.find('请求次数过多') != -1:
            raise RateLimitException(f'{self.get_name()}{err_msg}')

    @retry(wait=wait_fixed(3), stop=stop_after_attempt(3))
    async def get_detail(self, url) -> Optional[TorrentDetail]:
        detail_config = self.site_config.get('detail')
        if not detail_config:
            return
        async with httpx.AsyncClient(
                headers=self.headers,
                cookies=self.cookies,
                timeout=Timeout(timeout=self.download_timeout),
                proxies=self.proxies,
                follow_redirects=True,
                verify=False
        ) as client:
            r = await self._check_and_get_response(await client.get(url))
            text = self._get_response_text(r)
            if not text:
                return
            with SiteParser(self.site_config, PyQuery(text)) as parser:
                detail_result = parser.parse_detail()
            return TorrentDetail.build(self.site_config, detail_result)

    @retry(stop=stop_after_delay(300), wait=wait_exponential(multiplier=1, min=30, max=120), reraise=True)
    async def download(self, url, filepath):
        async with download_limiter.ratelimit(self.get_id(), delay=True):
            async with httpx.AsyncClient(
                    headers=self.headers,
                    cookies=self.cookies,
                    timeout=Timeout(timeout=self.download_timeout),
                    proxies=self.proxies,
                    follow_redirects=True,
                    verify=False
            ) as client:
                if self.get_download_method() == 'POST':
                    if self.get_download_content_type():
                        headers = self.headers
                        headers['content-type'] = self.get_download_content_type()
                        r = await client.post(url, data=self.get_download_args(), headers=headers)
                    else:
                        r = await client.post(url, data=self.get_download_args())
                else:
                    r = await client.get(url)
                if r.status_code == 404:
                    return
                if 'content-type' in r.headers and r.headers['content-type'].find('text/html') != -1:
                    if r.text.find(
                            '下载提示') != -1 or r.text.find('下載輔助說明') != -1:
                        match_id = re.search(r'name="id"\s+value="(\d+)"', r.text)
                        if match_id:
                            r = await client.post(f'{self.get_domain()}downloadnotice.php',
                                                  data={'id': match_id.group(1), 'type': 'ratio'})
                        else:
                            raise RuntimeError(
                                '%s下载种子需要页面确认，先手动打开浏览器下载一次，并重新换Cookie！' % self.get_name())
                    else:
                        self.__check_limit__(r.text, '下载频率过高：%s' % url)
                        logging.error(f'下载种子错误：%s' % url)
                        logging.error('%s' % r.text)
                        raise RuntimeError(f'{self.get_name()}下载出错')
                if r.status_code == 404:
                    return
                async with aiofiles.open(filepath, 'wb') as file:
                    await file.write(r.content)
