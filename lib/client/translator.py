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

# translation_task -> [ region, words, result ]
translation_task = [ None, None, None ]


def preprocess(words, separator):
    lines = [l.lstrip(separator) for l in words.split("\n")]
    words = " ".join([l for l in lines if l])
    return words


class TranslatorCommand(sublime_plugin.TextCommand):
    style = "popup"
    mdpopups_css = "Packages/DynamicMenus/mdpopups.css"

    def run(self, edit, keyboard=False, do_replace=False):
        view = self.view

        if keyboard and not self.get_words(view):
            sublime.status_message("No words to be translate.")

        elif do_replace:
            view.replace(edit, translation_task[0], translation_task[2])
            translation_task[0] = translation_task[2] = None
            return

        else:
            Loger.threading(self.do_translate, "Translating...", "Succeed.")

    def get_words(self, view):
        if view.has_non_empty_selection_region():
            selected = view.sel()[0]
            words = view.substr(selected)
            words = preprocess(words, MenusTranslator.separator)
            if len(words) > 0:
                translation_task[0] = selected
                translation_task[1] = words
                return True
        region = view.word(view.sel()[0])
        word = view.substr(region).strip(MenusTranslator.separator)
        if len(word) > 0:
            translation_task[0] = region
            translation_task[1] = word
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
        if href == "replace":
            self.view.run_command(self.name(), {"do_replace": True})

        elif href == "copy":
            sublime.set_clipboard(translation_task[2])
            sublime.status_message("Translation copied to clipboard")

    def display(self, words, received):
        pops = {
            "popup": self.show_popup,
            "phantom": self.show_phantom,
        }

        if self.style in pops:
            show = pops[self.style]
            show(translation_task[0], self.gen_markdown_text(words, received))

        elif self.style == "view":
            self.show_view(sublime.encode_value(received, pretty=True))

    def do_translate(self):
        pass

    def gen_markdown_text(self, words, received):
        return ""


TRANSLATOR_TEMPLATE = """
---
allow_code_wrap: true
---
!!! {}
"""

COPY_AND_REPLACE = """
<span class="copy"><a href=copy>Copy</a></span>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span class="replace"><a href=replace>Replace</a></span>
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

        q = translation_task[1]
        translation_task[1] = None

        platform = MenusTranslator.platforms["youdao"]
        if ("app_id" in platform and "app_key" in platform and
            "api_url" in platform):
            apiurl = platform["api_url"]
            appKey = platform["app_id"]
            secret = platform["app_key"]

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
            apiurl = "https://fanyi.youdao.com/openapi.do?keyfrom=divinites&key=1583185521&type=data&doctype=json&version=1.1&q=%s" % q

        try:
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            response = requests.post(apiurl, data=data, headers=headers)
            received = json.loads(response.content.decode('utf-8'))
        except Exception as e:
            sublime.error_message(u"数据请求失败！")
        else:
            self.display(q, received)

    # TODO: Use jieba to extract words, and then
    # combine those words as a sentence in proper
    # length, with considering the width of char.
    def gen_markdown_text(self, words, received):
        thread = "\n------------------------\n{}"
        body = TRANSLATOR_TEMPLATE.format("Youdao")
        footer = """<div class="footer">"""

        body += "## 原文：\n"
        body += words + "\n"

        if "basic" in received and received["basic"]:
            body += "## 解释：\n"
            for explain in received["basic"]["explains"]:
                body += "- {}\n".format(explain)

        if "translation" in received:
            body += "## 翻译：\n"
            explains = []
            for explain in received["translation"]:
                explains.append(explain)
                explain = "\n".join([
                    explain[i:i+24]
                    for i in range(0, len(explain), 24)
                ])
                body += "- {}\n".format(explain)
            translation_task[2] = "\n".join(explains)
            body += COPY_AND_REPLACE

        if "web" in received:
            body += thread.format("## 网络释义:\n")
            for explain in received["web"]:
                explains = ",".join(explain["value"])
                body += "`{}`: {}\n".format(explain["key"], explains)
        footer += """<span class="hide"><a href=hide>×</a></span></div>"""

        return body + thread.format(footer)


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
                translation_task[0] = selected
                translation_task[1] = words
                return True

        if self.auto_select is True:
            pt = view.window_to_text((event["x"], event["y"]))
            region = view.word(pt)
            word = view.substr(region).strip(self.separator)
            if len(word) > 0:
                translation_task[0] = region
                translation_task[1] = word
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
