import logging

from cssselect import SelectorSyntaxError
from pyquery import PyQuery

from moviebotapi.site import TorrentList, Torrent

from autoptspider.site.htmlparser import HtmlParser
from autoptspider.site.siteexceptions import SiteParseException, LoginRequired

_LOGGER = logging.getLogger(__name__)


class SiteParser:
    def __init__(self, site_config, doc: PyQuery = None, torrents_rule=None):
        self.site_config = site_config
        if torrents_rule:
            self.torrents_rule = torrents_rule
        else:
            self.torrents_rule = self.site_config.get('torrents')
        self.doc = doc

    def test_login(self):
        login_config = self.site_config.get('login')
        if not login_config:
            return True
        required = login_config.get('required')
        if required is not None and required is False:
            return True
        if not self.doc:
            return False
        test = login_config.get('test')
        try:
            if self.doc(test.get('selector')):
                return True
            else:
                return False
        except SelectorSyntaxError as e:
            raise SiteParseException(self.site_config.get('id'), self.site_config.get('name'),
                                     f"{self.site_config.get('name')}登陆检测使用了错误的CSS选择器：{str(e)}")
        except Exception as e:
            raise SiteParseException(self.site_config.get('id'), self.site_config.get('name'),
                                     f"{self.site_config.get('name')}登陆检测出现错误：{str(e)}")

    def parse_userinfo(self):
        if not self.test_login():
            raise LoginRequired(self.site_config.get('id'), self.site_config.get('name'),
                                f'{self.site_config.get("name")}登陆失败！')
        user_rule = self.site_config.get('userinfo')
        if not user_rule:
            return
        field_rule = user_rule.get('fields')
        if not field_rule:
            return
        constant = user_rule.get('constant', False)
        if constant:
            return user_rule.get('fields')
        try:
            item_tag = self.doc(user_rule.get('item')['selector'])
            result = HtmlParser.parse_item_fields(item_tag, field_rule)
            return result
        except SelectorSyntaxError as e:
            raise SiteParseException(self.site_config.get('id'), self.site_config.get('name'),
                                     f"{self.site_config.get('name')}解析用户信息使用了错误的CSS选择器：{str(e)}")
        except Exception as e:
            raise SiteParseException(self.site_config.get('id'), self.site_config.get('name'),
                                     f"{self.site_config.get('name')}解析用户信息出现错误：{str(e)}")

    def parse_detail(self):
        if not self.test_login():
            raise LoginRequired(self.site_config.get('id'), self.site_config.get('name'),
                                f'{self.site_config.get("name")}登陆失败！')
        detail_config = self.site_config.get('detail')
        if not detail_config:
            return
        field_rule = detail_config.get('fields')
        if not field_rule:
            return
        try:
            item_tag = self.doc(detail_config.get('item')['selector'])
            result = HtmlParser.parse_item_fields(item_tag, field_rule)
            return result
        except SelectorSyntaxError as e:
            raise SiteParseException(self.site_config.get('id'), self.site_config.get('name'),
                                     f"{self.site_config.get('name')}种子详情页解析使用了错误的CSS选择器：{str(e)}")
        except Exception as e:
            raise SiteParseException(self.site_config.get('id'), self.site_config.get('name'),
                                     f"{self.site_config.get('name')}种子详情页解析失败")

    def parse_torrents(self, context=None) -> TorrentList:
        if not self.torrents_rule:
            return []
        list_rule = self.torrents_rule.get('list')
        fields_rule = self.torrents_rule.get('fields')
        if not fields_rule:
            return []
        try:
            rows = self.doc(list_rule['selector'])
            if not rows:
                return []
            result: TorrentList = []
            for i in range(rows.length):
                tag = rows.eq(i)
                item = HtmlParser.parse_item_fields(tag, fields_rule, context=context)
                result.append(Torrent.build_by_parse_item(self.site_config, item))
            return result
        except SelectorSyntaxError as e:
            raise SiteParseException(self.site_config.get('id'), self.site_config.get('name'),
                                     f"{self.site_config.get('name')}种子信息解析使用了错误的CSS选择器：{str(e)}")
        except Exception as e:
            raise SiteParseException(self.site_config.get('id'), self.site_config.get('name'),
                                     f"{self.site_config.get('name')}种子信息解析失败")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.doc:
            del self.doc
