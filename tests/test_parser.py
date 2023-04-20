import asyncio
import os

from moviebotapi.site import CateLevel1

from autoptspider.site.sitehelper import SiteHelper
import yaml

TMPL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')


def load_yaml_config(filepath: str):
    """
    加载一个yaml格式的文件
    :param filepath:
    :return:
    """
    if not filepath or not os.path.exists(filepath):
        raise FileNotFoundError(f'找不到配置文件: {filepath}')
    with open(filepath, 'r', encoding='utf-8') as file:
        user_config = yaml.safe_load(file)
    return user_config


def get_mteam():
    """
    初始化一个mteam的爬虫类
    :return:
    """
    helper = SiteHelper(load_yaml_config(os.path.join(TMPL_PATH, 'mteam.yml')),
                        '换自己的tokens',
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36')
    return helper


def test_search():
    """
    获取馒头的爬虫类后进行搜索测试
    :return:
    """
    helper = get_mteam()
    res = asyncio.run(helper.search('星际穿越', cate_level1_list=[CateLevel1.Movie]))
    assert len(res) > 0
