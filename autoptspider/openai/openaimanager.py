import openai

from autoptspider.exceptions import ChatGPTException


class OpenAIManager:
    @staticmethod
    def set_api_key(api_key: str):
        openai.api_key = api_key
        # 使用国内可用的openai代理
        openai.api_base = "http://api.aiproxy.io/v1/"

    @staticmethod
    def get_response(messages: list):
        if not openai.api_key:
            raise ChatGPTException("尚未设置 OpenAI API Key，无法使用此功能")
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        print(res)
        return res["choices"][0]["message"]["content"]
