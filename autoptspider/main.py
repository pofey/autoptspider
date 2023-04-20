# python 入口main函数
from typing import Optional

import click

from autoptspider.openai.generator import NexusPHPGenerator
from autoptspider.openai.openaimanager import OpenAIManager


@click.command()
@click.option("--pt_domain", prompt="PT站点域名(http://xxx.com)", help="输入PT站点域名")
@click.option("--cookie_str", prompt="Cookie字符串", help="输入Cookie字符串")
@click.option("--user_agent", prompt="User-Agent", help="输入User-Agent")
def generate(pt_domain: str, cookie_str: str, user_agent: Optional[str]):
    generator = NexusPHPGenerator(pt_domain, cookie_str, user_agent)
    generator.start()


@click.command()
@click.option("--api_key", prompt="OpenAI API Key", help="输入OpenAI的 API Key")
def run(api_key: str):
    OpenAIManager.set_api_key(api_key)
    generate()


if __name__ == '__main__':
    run()
