import sublime
import sublime_plugin
import json
import shutil


import zipfile
import io
import os
import sys
import re

from threading import Thread
from .lib.urllib3 import PoolManager, make_headers
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

    # на удаленный сервер
    uploadPathComand = 'upload_path'
    uploadFileComand = 'upload_file'

    # с удаленного сервера
    downloadPathComand = 'download_path'
    downloadFileComand = 'download_file'

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
        headers={}
        if settings.get('user') and settings.get('password'):
            headers = make_headers(basic_auth=settings.get('user') + ':' + settings.get('password'))
            headers.update({"Authorization": headers.get('authorization')})
            headers.pop('authorization', None)
            pass
        self.headers=headers

    #Сохраняет файл на удаленный сервер
    def localToRemoteFile(self, filePath):
        manager = self.manager
        shortFileName = SublimePluginUtils.filePathInProject(filePath)
        with open(filePath, 'rb') as fp:
            file_data = fp.read()

        r = manager.request('POST', self.httpUrl+'/'+self.uploadFileComand, fields={
            'file': shortFileName,
            'fileData': (shortFileName, file_data, 'text/plain'),
        }, headers=self.headers)

        if r.status == 403:
            sublime.error_message(
                u'Ошибка аутентификации'
            )
            return

        if r.status != 200:
            sublime.error_message(
                u'Ошибка сохранения'
            )
            return


    #Сохраняет папки на удаленный сервер
    def localToRemotePath(self, filePath):
        manager = self.manager
        shortFileName = SublimePluginUtils.filePathInProject(filePath)
        with open(filePath, 'rb') as fp:
            file_data = fp.read()

        r = manager.request('POST', self.httpUrl+'/'+self.uploadPathComand, fields={
            'file': shortFileName,
            'pathData': (shortFileName, file_data, 'text/plain'),
        }, headers=self.headers)

        if r.status == 403:
            sublime.error_message(
                u'Ошибка аутентификации'
            )
            return

        if r.status != 200:
            sublime.error_message(
                u'Ошибка сохранения'
            )
            return

    #Обновление файла в локальной директории
    def remoteToLocalFile(self, filePath):
        if filePath is None:
            return

        manager = self.manager
        shortFileName = SublimePluginUtils.filePathInProject(filePath)
        r = manager.request('GET', self.httpUrl+'/'+self.downloadFileComand,  fields={'file': shortFileName}, headers=self.headers)

        if r.status == 403:
            sublime.error_message(
                u'Ошибка аутентификации'
            )
            return

        if r.status == 404:
            sublime.error_message(
                u'Файл на сервере не найден'
            )
            return

        if r.status != 200:
            sublime.error_message(
                u'Ошибка сохранения'
            )
            return

        overloadedFile = open(filePath, "wb")
        overloadedFile.write(r.data)
        overloadedFile.close()

    #Обновление файла в локальной директории
    def remoteToLocalPath(self, filePath):
        if filePath is None:
            return
        manager = self.manager
        shortFileName = SublimePluginUtils.filePathInProject(filePath)
        r = manager.request('GET', self.httpUrl+'/'+self.downloadPathComand,  fields={'path': shortFileName}, headers=self.headers)

        if r.status == 403:
            sublime.error_message(
                u'Ошибка аутентификации'
            )
            return
        if r.status != 200:
            sublime.error_message(
                u'Ошибка сохранения'
            )
            return

        zf = zipfile.ZipFile(io.BytesIO(r.data), "r")

        SublimePluginUtils.clearFolder(filePath)
        zf.extractall(filePath)
        zf.close()
                
class SublimePluginUtils():

    # чистим папку
    def clearFolder(folderPath):

        # надо выпилить потом как нить
        configName = 'http-editor-config.json'
        for the_file in os.listdir(folderPath):
            if configName in the_file :
                continue

            file_path = os.path.join(folderPath, the_file)

            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):

                    shutil.rmtree(file_path)
            except Exception as e:
                print(e)


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
            if viewFilePath == path :
                return "/"

            if viewFilePath is not None and viewFilePath.startswith( path ):
                return viewFilePath.replace(path, "")
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
            print('Ошибка обработки файла настройки', e)
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

        configName = 'http-editor-config.json'
        view = sublime.active_window().active_view()
        if configName in view.file_name():
            pass

        transport = SessionView.get('transport')
        if transport is None:
            return

        transport.remoteToLocalFile(view.file_name())



class HttpEditorUploadPathCommand(sublime_plugin.WindowCommand):
    def run(self, paths):

        path = paths[0]
        configName = 'http-editor-config.json'
        if configName in path:
            pass
        rootPath = SublimePluginUtils.rootDirPath(path)
        transport = SessionRootPath.getFromPath(rootPath, 'transport')
        if transport is None:

            localSettingsPath = rootPath+'/'+configName
            jsonSettings = SublimePluginUtils.jsonData(localSettingsPath)
            if jsonSettings is None:
                return
            transport = HttpTransport(jsonSettings)

        if os.path.isfile(path):
            transport.remoteToLocalFile(path)
            return
        
        t = Thread(group=None, target=transport.remoteToLocalPath, name="T1", args=(path,), kwargs={})
        t.start()

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

class SessionRootPath():
    sharedAttrs = {}

    def setFromPath(externalPath, key, val):
        fullKey = str(externalPath)+'_'+key
        SessionView.sharedAttrs[fullKey] = val

    def getFromPath(externalPath, key):
        fullKey = str(externalPath)+'_'+key
        try:
            return SessionRootPath.sharedAttrs[fullKey]
            pass
        except Exception as e:
            return