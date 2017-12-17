import sublime
import sublime_plugin
import json


import os
import sys
import re

from .lib.urllib3 import PoolManager
from .http_editor.commands  import RemoteToLocalFileCommand
#import httplib

st_version = 2
if int(sublime.version()) > 3000:
    st_version = 3

# костыли для третьего sublime
if st_version == 3:
    from imp import reload
    mod_load_prefix = 'HttpEditor.'

class ITransportInterface:
    def localToRemoteFile(self, filePath): raise NotImplementedError

class HttpTransport():

    def __init__(self, settings):

        if settings.get('httpUrl'):
            httpUrl = settings.get('httpUrl')

        if settings.get('httpUrl') is None:

	        httpUrl = settings.get('type')+'://'+settings.get('host')
	        if settings.get('type'):
	            httpUrl = httpUrl+':'+settings.get('port')

	        if settings.get('uri'):
	            httpUrl = httpUrl+'/'+settings.get('uri')

        manager = PoolManager(10)
        # инициализируем переменные класса
        self.httpUrl = httpUrl
        self.manager = manager

    #Сохраняет файл на удаленный сервер
    def localToRemoteFile(self, filePath):
        manager = self.manager
        shortFileName = SublimePluginUtils.filePathInProject(filePath)
        with open(filePath, 'rb') as fp:
            file_data = fp.read()

        r = manager.request('POST', self.httpUrl, fields={
            'updatingFieldName': shortFileName,
            'updatingField': (shortFileName, file_data, 'text/plain'),
        })


    #Обновление файла в локальной директории
    def remoteToLocalFile(self, filePath):
        if filePath is None:
            return
        manager = self.manager
        shortFileName = SublimePluginUtils.filePathInProject(filePath)
        r = manager.request('GET', self.httpUrl,  fields={'downloadFileName': shortFileName})
        overloadedFile = open(filePath, "wb")
        overloadedFile.write(r.data)
        overloadedFile.close()


class SessionView():
    sharedAttrs = {}

    def setFromView(externalView, key, val):
        fullKey = str(externalView.buffer_id())+'_'+key
        SessionView.sharedAttrs[fullKey] = val

    def set(key, val):
        curentView = sublime.active_window().active_view()
        fullKey = str(curentView.buffer_id())+'_'+key
        SessionView.sharedAttrs[fullKey] = val


    def get(key):
        curentView = sublime.active_window().active_view()
        fullKey = str(curentView.buffer_id())+'_'+key
        try:
	        return SessionView.sharedAttrs[fullKey]            
        	pass
        except Exception as e:
        	return


class SublimePluginUtils():
    # Определяет рутовый каталог по файлу
    def rootDirPath(viewFilePath):
        curentWindow = sublime.active_window()
        folderPath = curentWindow.folders()

        for path in folderPath:
            if  viewFilePath is not None and viewFilePath.startswith( path ):
                return path
                pass
            pass

        return folderPath[0]

    def filePathInProject(viewFilePath):
        curentWindow = sublime.active_window()
        folderPath = curentWindow.folders()
        for path in folderPath:
            if viewFilePath is not None and viewFilePath.startswith( path ):
                return viewFilePath.replace(path+'/', "")
                pass
            pass

        return viewFilePath

    def jsonData(settingPath):
        RE_COMMENTS = re.compile('[^:]\/\/[^\\n]*',  re.S)
        try:
            with open(settingPath) as f:
                content = f.read()
            pass
        except Exception as e:
            return

        jsonObj = json.loads(RE_COMMENTS.sub('', content))
        return jsonObj


class HttpEditor(sublime_plugin.ViewEventListener):

    def __init__(self, view):

        configName = 'http-editor-config.json'
        if view.file_name() is not None and configName in view.file_name():
            return
            pass

        rootPath = SublimePluginUtils.rootDirPath(view.file_name())

        localSettingsPath = rootPath+'/'+configName
        jsonSettings = SublimePluginUtils.jsonData(localSettingsPath)
        if jsonSettings is None:
            return
        transport = HttpTransport(jsonSettings)
        SessionView.setFromView(view, 'transport', transport)
        transport.remoteToLocalFile(view.file_name())

    @classmethod
    def is_applicable(cls, settings):
        return True


class HttpEditorListener(sublime_plugin.EventListener):

    def on_post_save(self, view):
        transport = SessionView.get('transport')
        if transport is None:
            return
        transport.localToRemoteFile(view.file_name())

class HttpEditorUploadCommand(sublime_plugin.WindowCommand):
    def run(self, paths):
        view = sublime.active_window().active_view()
        transport = SessionView.get('transport')
        if transport is None:
            return

        transport.remoteToLocalFile(view.file_name())



