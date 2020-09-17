import os
import json

import sublime
import sublime_plugin

from .lib.log import Loger
from .lib.client.opener import MenusOpener, OpenOtherFilesCommand
from .lib.client.searcher import MenusSearcher, SearchOnlineCommand
from .lib.client.translator import (
    MenusTranslator, TranslatorCommand,
    YoudaoTranslator, GoogleTranslator
)


class DynamicMenusToggleLogCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        Loger.debug = not Loger.debug


def load_plugin(plugin):
    def load_settings():
        translator = settings.get("translator", {})
        search_online = settings.get("search_online", {})
        open_other_files = settings.get("open_other_files", {})
        TranslatorCommand.style = translator.get("style", "popup")
        TranslatorCommand.mdpopups_css = translator.get("mdpopups.css",
            "Packages/DynamicMenus/mdpopups.css")

        caption = open_other_files.get("caption", "Open Other File")
        enabled = open_other_files.get("enabled", True)
        plugin.menus_opener.__init__(caption, enabled)

        caption = translator.get("caption", "Translator")
        auto_select = translator.get("auto_select", True)
        platforms = translator.get("platforms", {})
        separator = translator.get("separator",
            "|\\\n\f/:,;<>.+=-_~`'\"!@#$%^&*({[（《：；·，。—￥？！……‘’“”、》）]})")
        plugin.menus_translator.__init__(caption, auto_select,
            platforms, separator)

        caption = search_online.get("caption", "Search Online")
        enabled = search_online.get("enabled", True)
        platforms = search_online.get("platforms", {})
        plugin.menus_searcher.__init__(caption, enabled, platforms)

    settings = sublime.load_settings("DynamicMenus.sublime-settings")
    settings.add_on_change("dynamic_menus", load_settings)
    load_settings()


def menus_cache_dir():
    return os.path.join(sublime.cache_path(), __package__)


def context_menus_cache_path():
    return os.path.join(menus_cache_dir(), "Context.sublime-menu")

def widget_context_menus_cache_path():
    return os.path.join(menus_cache_dir(), "Widget Context.sublime-menu")

def write_context_menus(menus):
    with open(context_menus_cache_path(), "w+") as cache:
        cache.write(json.dumps(menus))
    with open(widget_context_menus_cache_path(), "w+") as cache:
        cache.write(json.dumps(menus))

def plugin_loaded():
    os.makedirs(menus_cache_dir(), exist_ok=True)
    write_context_menus([])
    load_plugin(DynamicMenusEventListener)

def plugin_unloaded():
    try:
        os.remove(context_menus_cache_path())
        os.remove(widget_context_menus_cache_path())
    except:
        pass


class DynamicMenusEventListener(sublime_plugin.EventListener):
    menus_opener = MenusOpener()
    menus_searcher = MenusSearcher()
    menus_translator = MenusTranslator()

    def on_post_text_command(self, view, command, args):
        if command == "context_menu":
            write_context_menus([])

    def on_text_command(self, view, command, args):
        def add_dynamic_menu(menus):
            if menus:
                dynamic_menus.append(menus)

        if command == "context_menu" and args and "event" in args:
            event = args['event']
            dynamic_menus = []
            add_dynamic_menu(self.menus_translator.create(view, event))
            add_dynamic_menu(self.menus_searcher.create(view, event))
            add_dynamic_menu(self.menus_opener.create(view, event))

            if dynamic_menus:
                write_context_menus(dynamic_menus)


    # Just for reloading this plugin.
    # """
    def on_post_save(self, view):
        path = view.file_name()
        dir = os.path.dirname(__file__)
        if path.endswith(".py") and path.startswith(dir) and path != __file__:
            start = len(sublime.packages_path())+1
            modulename = path[start:-3]
            if path.endswith("__init__.py"):
                modulename = modulename[:-9]
            modulename = modulename.replace("/", ".")
            modulename = modulename.replace("\\", ".")
            sublime_plugin.reload_plugin(modulename)
            sublime_plugin.reload_plugin(
                "{}.builder".format(__package__))
    # """
