import re
import json
import uuid
import time
import hashlib
import requests
import mdpopups

import sublime
import sublime_plugin

from ..menus_creator import MenusCreator
from ..log import Loger


class task:
    succeed_message = "Succeed."
    failed_message = "Failed!"
    region = None
    words = None
    result = None


def preprocess(words, separator):
    lines = [l.lstrip(separator) for l in words.split("\n")]
    words = " ".join([l for l in lines if l])
    return words


class TranslatorCommand(sublime_plugin.TextCommand):
    style = "popup"
    mdpopups_css = "Packages/DynamicMenus/mdpopups.css"

    def run(self, edit, action="translate"):
        view = self.view

        if action == "translate":
            if self.get_words(view):
                Loger.threading(self.do_translate, "Translating...")
            else:
                sublime.status_message("No words to be translate.")

        elif action == "copy":
            sublime.set_clipboard(task.result)
            sublime.status_message("Translation copied to clipboard")

        elif action == "insert":
            view.insert(edit, task.region.end(), "\n%s\n" % task.result)
            task.region = task.result = None

        elif action == "replace":
            view.replace(edit, task.region, task.result)
            task.region = task.result = None


    def get_words(self, view):
        if view.has_non_empty_selection_region():
            selected = view.sel()[0]
            words = view.substr(selected)
            words = preprocess(words, MenusTranslator.separator)
            if len(words) > 0:
                task.region = selected
                task.words = words
                return True
        region = view.word(view.sel()[0])
        word = view.substr(region).strip(MenusTranslator.separator)
        if len(word) > 0:
            task.region = region
            task.words = word
            return True
        return False

    def show_popup(self, region, content):
        def on_navigate(href):
            self.handle_href(href)
            self.view.hide_popup()

        mdpopups.show_popup(
            view=self.view,
            css=sublime.load_resource(self.mdpopups_css),
            max_width=480,
            max_height=320,
            location=(region.a + region.b)//2,
            content=content,
            on_navigate=on_navigate,
            md=True)

    def show_phantom(self, region, content):
        def on_navigate(href):
            self.handle_href(href)
            self.view.erase_phantoms("Translator")

        mdpopups.add_phantom(
            view=self.view,
            css=sublime.load_resource(self.mdpopups_css),
            key="Translator",
            region=region,
            content=content,
            layout=sublime.LAYOUT_BELOW,
            on_navigate=on_navigate,
            md=True)

    def show_view(self, content):
        view = self.view.window().new_file(
            flags=sublime.TRANSIENT,
            syntax="Packages/JavaScript/JSON.sublime-syntax")

        view.set_scratch(True)
        view.set_name("Translation")
        view.run_command("append", {"characters": content})

    def handle_href(self, href):
        self.view.run_command(self.name(), {"action": href})

    def display(self, words, resdict):
        pops = {
            "popup": self.show_popup,
            "phantom": self.show_phantom,
        }

        if self.style in pops:
            show = pops[self.style]
            show(task.region, self.gen_markdown_text(words, resdict))

        elif self.style == "view":
            self.show_view(sublime.encode_value(resdict, pretty=True))

    def do_translate(self):
        pass

    def gen_markdown_text(self, words, resdict):
        return ""


TRANSLATOR_TEMPLATE = """
---
allow_code_wrap: true
---
!!! {}
"""

COPY_INSERT_REPLACE = """
<span class="copy"><a href=copy>Copy</a></span>&nbsp;&nbsp;&nbsp;&nbsp;<span class="insert"><a href=insert>Insert</a></span>&nbsp;&nbsp;&nbsp;&nbsp;<span class="replace"><a href=replace>Replace</a></span>
"""


class YoudaoTranslator(TranslatorCommand):
    def do_translate(self):
        def truncate(q):
            size = len(q)
            return q if size <= 20 else q[0:10] + str(size) + q[size - 10:size]

        def encrypt(signStr):
            hash_algorithm = hashlib.sha256()
            hash_algorithm.update(signStr.encode('utf-8'))
            return hash_algorithm.hexdigest()

        q = task.words
        task.words = None

        platform = MenusTranslator.platforms["youdao"]
        apiurl = platform.get("api_url", "")
        appKey = platform.get("app_id", "")
        secret = platform.get("app_key", "")
        if (apiurl and appKey and secret):
            curtime = str(int(time.time()))
            salt = str(uuid.uuid1())
            sign = encrypt(appKey + truncate(q) + salt + curtime + secret)
            data = {
                "q": q,
                "from": platform["from"],
                "to": platform["to"],
                "appKey": appKey,
                "salt": salt,
                "sign": sign,
                "signType": "v3",
                "curtime": curtime
            }

        else:
            data = { "q": q }
            apiurl = "http://fanyi.youdao.com/openapi.do?keyfrom=divinites&key=1583185521&type=data&doctype=json&version=1.1"

        try:
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            Loger.print("youdao translator: begin requests.post")
            Loger.done_msg = task.failed_message
            response = requests.post(apiurl,
                data=data, headers=headers, timeout=(1, 5))
            Loger.done_msg = task.succeed_message
            Loger.print("youdao translator: end requests.post")
            resdict = json.loads(response.content.decode('utf-8'))
        except requests.exceptions.ConnectionError:
            Loger.error(u"连接失败，请检查你的网络状态")
        except requests.exceptions.ConnectTimeout:
            Loger.error(u"连接超时，请检查你的网络状态")
        except Exception:
            Loger.error(u"数据请求失败！")
        else:
            self.display(q, resdict)

    # TODO: Use jieba to extract words, and then
    # combine those words as a sentence in proper
    # length, with considering the width of char.
    def gen_markdown_text(self, words, resdict):
        line = "\n------------------------\n{}"
        body = TRANSLATOR_TEMPLATE.format("Youdao")
        footer = """<div class="footer">"""

        body += "## 原文：\n"
        body += words + "\n"

        if "basic" in resdict and resdict["basic"]:
            body += "## 解释：\n"
            for explain in resdict["basic"]["explains"]:
                body += "- {}\n".format(explain)

        if "translation" in resdict:
            body += "## 翻译：\n"
            explains = []
            for explain in resdict["translation"]:
                explains.append(explain)
                explain = "\n".join([
                    explain[i:i+24]
                    for i in range(0, len(explain), 24)
                ])
                body += "- {}\n".format(explain)
            task.result = "\n".join(explains)
            body += COPY_INSERT_REPLACE

        if "web" in resdict:
            body += line.format("## 网络释义:\n")
            for explain in resdict["web"]:
                explains = ",".join(explain["value"])
                body += "`{}`: {}\n".format(explain["key"], explains)
        footer += """<span class="hide"><a href=hide>×</a></span></div>"""

        return body + line.format(footer)


class GoogleTranslator(TranslatorCommand):
    pass


class MenusTranslator(MenusCreator):
    def __init__(self, caption="Translator", auto_select=True, platforms={},
        separator=( "|\\\n\f/:,;<>.+=-_~`'\"!@#$%^&*"
                    "({[（《：；·，。—￥？！……‘’“”、》）]})")):
        MenusTranslator.caption = caption
        MenusTranslator.platforms = platforms
        MenusTranslator.separator = separator
        MenusTranslator.auto_select = auto_select

    def item(self, caption, command):
        return { "caption": caption, "command": command }

    def get_words_with_event(self, view, event):
        if view.has_non_empty_selection_region():
            selected = view.sel()[0]
            words = view.substr(selected)
            words = preprocess(words, self.separator)
            if len(words) > 0:
                task.region = selected
                task.words = words
                return True

        if self.auto_select is True:
            pt = view.window_to_text((event["x"], event["y"]))
            region = view.word(pt)
            word = view.substr(region).strip(self.separator)
            if len(word) > 0:
                task.region = region
                task.words = word
                return True
        return False

    def create(self, view, event):
        if len(self.platforms) > 0:
            if self.get_words_with_event(view, event):
                items = []
                for p in sorted(self.platforms):
                    platform = self.platforms[p]
                    if platform.get("enabled", True):
                        caption = platform.get("caption", p.title())
                        command = "{}_translator".format(p.lower())
                        items.append(self.item(caption, command))
                if len(items) > 1:
                    return self.fold_items(items)
                if len(items) == 1:
                    return items[0]
        return None
