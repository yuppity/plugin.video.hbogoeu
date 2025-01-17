# encoding: utf-8
# Hbo Spain and Nordic handler class for Hbo Go Kodi add-on
# Copyright (C) 2019 Sakerdot (https://github.com/Sakerdot)
# Copyright (C) 2019 ArvVoid (https://github.com/arvvoid)
# Relesed under GPL version 2
#########################################################
# HBO Spain and Nordic HANDLER CLASS
#########################################################

from hbogolib.handler import HbogoHandler
from hbogolib.constants import HbogoConstants
from hbogolib.ttml2srt import Ttml2srt

import sys
import base64
import urllib
import time
import hashlib
import xml.etree.ElementTree as ET

import xbmc
import xbmcgui
import xbmcplugin
import inputstreamhelper

import requests
import os
import errno

class HbogoHandler_sp(HbogoHandler):

    def __init__(self, handle, base_url, country):
        HbogoHandler.__init__(self, handle, base_url)

        self.LICENSE_SERVER = ""

        self.API_CLIENT_VERSION = '3.8.3'
        self.API_DEVICE_ID = ''
        self.API_DEVICE_TOKEN = ''
        self.API_IDENTITY_GUID = ''
        self.API_ACCOUNT_GUID = ''

        self.NAMESPACES = {
            'clearleap': 'http://www.clearleap.com/namespace/clearleap/1.0/',
            'media': 'http://search.yahoo.com/mrss/',
        }

        if country[1] == 'es':
            self.API_HOST = 'api-hboe.hbo.clearleap.com'
        else:
            self.API_HOST = 'api-hbon.hbo.clearleap.com'

        self.API_HOST_GATEWAY = country[5]
        self.API_HOST_GATEWAY_REFERER = self.API_HOST_GATEWAY + '/sign-in'

        self.DEFAULT_LANGUAGE = country[4]
        self.LANGUAGE_CODE = self.DEFAULT_LANGUAGE
        if self.language(30000) == 'ENG':  # only englih or the default language for the selected operator is allowed
            if country[1] == 'es':
                self.LANGUAGE_CODE = 'en_hboespana'
            else:
                self.LANGUAGE_CODE = 'en_hbon'

        # check if default language is forced
        if self.addon.getSetting('deflang') == 'true':
            self.LANGUAGE_CODE = self.DEFAULT_LANGUAGE

        self.API_URL_BROWSE = 'https://' + self.API_HOST + '/cloffice/client/web/browse/'
        self.LANGUAGE_CODE = '?language='+self.LANGUAGE_CODE
        self.API_URL_AUTH_WEBBASIC = 'https://' + self.API_HOST + '/cloffice/client/device/login'

        if len(self.getCredential('username')) == 0:
            self.setup()
        else:
            self.init_api()

    def genContextMenu(self, content_id, media_id):
        add_mylist = (self.language(30719).encode('utf-8'), 'RunPlugin(' + self.base_url + "?url=ADDMYLIST&mode=9&cid=" + media_id + ')')
        remove_mylist = (self.language(30720).encode('utf-8'), 'RunPlugin(' + self.base_url + "?url=REMMYLIST&mode=10&cid=" + media_id + ')')

        vote_5 = (self.language(30721).encode('utf-8'), 'RunPlugin(' + self.base_url + "?url=VOTE&mode=8&vote=5&cid=" + content_id + ')')
        vote_4 = (self.language(30722).encode('utf-8'), 'RunPlugin(' + self.base_url + "?url=VOTE&mode=8&vote=4&cid=" + content_id + ')')
        vote_3 = (self.language(30723).encode('utf-8'), 'RunPlugin(' + self.base_url + "?url=VOTE&mode=8&vote=3&cid=" + content_id + ')')
        vote_2 = (self.language(30724).encode('utf-8'), 'RunPlugin(' + self.base_url + "?url=VOTE&mode=8&vote=2&cid=" + content_id + ')')
        vote_1 = (self.language(30725).encode('utf-8'), 'RunPlugin(' + self.base_url + "?url=VOTE&mode=8&vote=1&cid=" + content_id + ')')

        if self.cur_loc == self.LB_MYPLAYLIST:
            return [vote_5, vote_4, vote_3, vote_2, vote_1, remove_mylist]
        else:
            return [add_mylist, vote_5, vote_4, vote_3, vote_2, vote_1]

    def generate_device_id(self):
        import uuid
        return str(uuid.uuid4())

    def chk_login(self):
        return self.API_DEVICE_TOKEN != ''

    def login(self):
        username = self.getCredential('username')
        password = self.getCredential('password')

        headers = {
            'Host': self.API_HOST,
            'User-Agent': self.UA,
            'Accept': '*/*',
            'Accept-Language': self.ACCEPT_LANGUAGE,
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': self.API_HOST_GATEWAY_REFERER,
            'Content-Type': 'application/xml',
            'Authorization': 'Basic ' + base64.b64encode(username + ':' + base64.b64encode(password)),
            'Origin': self.API_HOST_GATEWAY,
            'Connection': 'keep-alive',
        }

        self.API_DEVICE_ID = self.addon.getSetting('individualization')

        if self.API_DEVICE_ID == "":
            self.log("NO REGISTRED DEVICE - generating")
            self.API_DEVICE_ID = self.generate_device_id()
            self.addon.setSetting('individualization', str(self.API_DEVICE_ID))

        self.log("DEVICE ID: " + str(self.API_DEVICE_ID))
        login_hash = hashlib.sha224(str(self.API_DEVICE_ID) + str(username) + str(password)).hexdigest()
        self.log("LOGIN HASH: " + login_hash)

        loaded_session = self.load_obj(self.addon_id + "_es_session")

        if loaded_session is not None:
            self.log("SAVED SESSION LOADED")
            if loaded_session["hash"] == login_hash:
                self.log("HASH IS VALID")
                if time.time() < (loaded_session["time"] + (self.SESSION_VALIDITY * 60 * 60)):
                    self.log("NOT EXPIRED RESTORING...")
                    self.API_DEVICE_TOKEN = loaded_session["API_DEVICE_TOKEN"]
                    self.API_IDENTITY_GUID = loaded_session["API_IDENTITY_GUID"]
                    self.API_ACCOUNT_GUID = loaded_session["API_ACCOUNT_GUID"]
                    self.init_api()
                    loaded_session['time'] = time.time()
                    self.save_obj(loaded_session, self.addon_id + "_es_session")
                    return True

        data = '<device><type>web</type><deviceId>' + self.API_DEVICE_ID + '</deviceId></device>'

        response = self.send_login_hbogo(self.API_URL_AUTH_WEBBASIC, headers, data, 'xml')

        if response.find('status').text == 'Success':
            self.API_DEVICE_TOKEN = response.find('token').text
            self.API_IDENTITY_GUID = response.find('identityGuid').text
            self.API_ACCOUNT_GUID = response.find('accountGuid').text
            self.init_api()

            login_hash = hashlib.sha224(str(self.API_DEVICE_ID) + str(username) + str(password)).hexdigest()
            self.log("LOGIN HASH: " + login_hash)
            saved_session = {

                "hash": login_hash,
                "API_DEVICE_TOKEN": self.API_DEVICE_TOKEN,
                "API_IDENTITY_GUID": self.API_IDENTITY_GUID,
                "API_ACCOUNT_GUID": self.API_ACCOUNT_GUID,
                "time": time.time()

            }
            self.save_obj(saved_session, self.addon_id + "_es_session")

            return True
        else:
            return False

    def setup(self):
        self.init_api()
        if self.inputCredentials():
            return True
        else:
            self.del_setup()
            xbmcgui.Dialog().ok(self.LB_ERROR, self.language(30444).encode('utf-8'))
            sys.exit()
            return False

    def init_api(self):
        self.loggedin_headers = {
            'Host': self.API_HOST,
            'User-Agent': self.UA,
            'Accept': '*/*',
            'Accept-Language': self.ACCEPT_LANGUAGE,
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': self.API_HOST_GATEWAY_REFERER,
            'X-Client-Name': 'web',
            'X-Client-Version': self.API_CLIENT_VERSION,
            'X-Clearleap-DeviceId': self.API_DEVICE_ID,
            'X-Clearleap-DeviceToken': self.API_DEVICE_TOKEN,
            'Origin': self.API_HOST_GATEWAY,
            'Connection': 'keep-alive',
        }

    def categories(self):
        if not self.chk_login():
            self.login()

        browse_xml = self.get_from_hbogo(self.API_URL_BROWSE+self.LANGUAGE_CODE, response_format='xml')

        home = None
        series = None
        movies = None
        kids = None

        for item in browse_xml.findall('.//item'):
            if item.find('category').text == 'Home':
                home = item
            elif item.find('category').text == 'Series':
                series = item
            elif item.find('category').text == 'Movies':
                movies = item
            elif item.find('category').text == 'Kids' or item.find('category').text == 'Toonix':
                kids = item
            else:
                pass

        if series is not None:
            self.addCat(series.find('title').text.encode('utf-8'), series.find('link').text, self.md + 'tv.png', 1)
        else:
            self.log("No Series Category found")
        
        if movies is not None:
            self.addCat(movies.find('title').text.encode('utf-8'), movies.find('link').text, self.md + 'movie.png', 1)
        else:
            self.log("No Movies Category found")

        if kids is not None:
            self.addCat(kids.find('title').text.encode('utf-8'), kids.find('link').text, self.md + 'kids.png', 1)
        else:
            self.log("No Kids Category found")

        if home is not None:
            self.list(home.find('link').text, True)
        else:
            self.log("No Home Category found")


        xbmcplugin.addSortMethod(
            handle=self.handle,
            sortMethod=xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.endOfDirectory(self.handle)

    def get_thumbnail_url(self, item):
        self.log("get thumbnail xml" + ET.tostring(item, encoding='utf8'))
        try:
            thumbnails = item.findall('.//media:thumbnail', namespaces=self.NAMESPACES)
            for thumb in thumbnails:
                if thumb.get('height') == '1080':
                    self.log("Huge Poster found, using as thumbnail")
                    return str(thumb.get('url'))
            for thumb in thumbnails:
                if thumb.get('height') == '720':
                    self.log("Large Poster found, using as thumbnail")
                    return str(thumb.get('url'))
            self.log("Poster not found using first one")
            return str(thumbnails[0].get('url'))
        except:
            self.log("Find thumbnail failed")
            return self.resources + 'fanart.jpg'

    def list_pages(self, url, max = 200, offset = 0):

        response = self.get_from_hbogo(url + self.LANGUAGE_CODE + "&max=" + str(max) + "&offset=" + str(offset), 'xml')

        count = 0

        for item in response.findall('.//item'):
            count += 1
            item_link = item.find('link').text

            if len(item_link) > 0:
                self.log(ET.tostring(item, encoding='utf8'))
                item_type = item.find('clearleap:itemType', namespaces=self.NAMESPACES).text.encode('utf-8')
                if item_type != 'media':
                    self.addDir(item)
                elif item_type == 'media':
                    self.addLink(item, 5)
                else:
                    self.log('Unknown item type: ' + item_type)
        self.log('List pages total items: ' + str(count))
        if count == max:
            self.log('List pages calling next page... max: '+ str(max) + ' offset: ' + str(offset+max))
            self.list_pages(url, max, offset+max)


    def list(self, url, simple=False):
        if not self.chk_login():
            self.login()
        self.log("List: " + str(url))

        if not self.chk_login():
            self.login()

        self.list_pages(url, 200, 0)
    
        if simple == False:
            xbmcplugin.addSortMethod(handle=self.handle, sortMethod=xbmcplugin.SORT_METHOD_UNSORTED)
            xbmcplugin.addSortMethod(handle=self.handle, sortMethod=xbmcplugin.SORT_METHOD_LABEL)
            xbmcplugin.addSortMethod(handle=self.handle, sortMethod=xbmcplugin.SORT_METHOD_TITLE)
            xbmcplugin.addSortMethod(handle=self.handle, sortMethod=xbmcplugin.SORT_METHOD_VIDEO_YEAR)
            xbmcplugin.addSortMethod(handle=self.handle, sortMethod=xbmcplugin.SORT_METHOD_GENRE)
            xbmcplugin.addSortMethod(handle=self.handle, sortMethod=xbmcplugin.SORT_METHOD_LASTPLAYED)
            xbmcplugin.setContent(self.handle, self.use_content_type)
            xbmcplugin.endOfDirectory(self.handle)
    
    def play(self, url, content_id):
        self.log("Play: " + str(url))

        if not self.chk_login():
            self.login()
        
        if not self.chk_login():
            self.log("NOT LOGGED IN, ABORTING PLAY")
            xbmcgui.Dialog().ok(self.LB_LOGIN_ERROR, self.language(30103).encode('utf-8'))
            self.logout()
            return

        media_item = self.get_from_hbogo(url+self.LANGUAGE_CODE, 'xml')

        self.log("Play Media: " + ET.tostring(media_item, encoding='utf8'))

        mpd_pre_url = media_item.find('.//media:content[@profile="HBO-DASH-WIDEVINE"]', namespaces=self.NAMESPACES).get('url') + '&responseType=xml'

        mpd = self.get_from_hbogo(mpd_pre_url, 'xml')
        self.log("Manifest: " + ET.tostring(mpd, encoding='utf8'))

        mpd_url = mpd.find('.//url').text
        self.log("Manifest url: " + str(mpd_url))

        media_guid = media_item.find('.//guid').text

        license_headers = 'X-Clearleap-AssetID=' + media_guid + '&X-Clearleap-DeviceId=' + self.API_DEVICE_ID + \
            '&X-Clearleap-DeviceToken=' + self.API_DEVICE_TOKEN + '&Content-Type='
    
        license_url = 'https://' + self.API_HOST + '/cloffice/drm/wv/' + media_guid + '|' + license_headers + '|R{SSM}|'

        li = xbmcgui.ListItem(path=mpd_url)
        protocol = 'mpd'
        drm = 'com.widevine.alpha'
        is_helper = inputstreamhelper.Helper(protocol, drm=drm)
        is_helper.check_inputstream()
        li.setProperty('inputstreamaddon', 'inputstream.adaptive')
        li.setProperty('inputstream.adaptive.license_type', drm)
        li.setProperty('inputstream.adaptive.manifest_type', protocol)
        li.setProperty('inputstream.adaptive.license_key', license_url)

        li.setMimeType('application/dash+xml')
        li.setContentLookup(False)
        #GET SUBTITLES
        folder = xbmc.translatePath(self.addon.getAddonInfo('profile'))
        folder = folder + 'subs' + os.sep + media_guid + os.sep
        if self.addon.getSetting('forcesubs') == 'true':
            self.log("Force subtitles enabled, downloading and converting subtitles in: " + str(folder))
            if not os.path.exists(os.path.dirname(folder)):
                try:
                    os.makedirs(os.path.dirname(folder))
                except OSError as exc:  # Guard against race condition
                    if exc.errno != errno.EEXIST:
                        raise
            try:
                subs = media_item.findall('.//media:subTitle', namespaces=self.NAMESPACES)
                subs_paths = []
                for sub in subs:
                    self.log("Processing subtitle language code: " + str(sub.get('lang')) + " URL: " + str(sub.get('href')))
                    r = requests.get(sub.get('href'))
                    with open(str(folder) + str(sub.get('lang')) + ".xml", 'wb') as f:
                        f.write(r.content)
                    ttml = Ttml2srt(str(folder) + str(sub.get('lang')) + ".xml", 25)
                    srt_file = ttml.write_srt_file(str(folder) + str(sub.get('lang')))
                    self.log("Subtitle converted to srt format")
                    subs_paths.append(srt_file)
                    self.log("Subtitle added: " + srt_file)
                self.log("Setting subtitles: " + str(subs_paths))
                li.setSubtitles(subs_paths)
                self.log("Subtitles set")
            except:
                self.log("Unexpected error in subtitles processing")

        self.log("Play url: " + str(li))
        xbmcplugin.setResolvedUrl(self.handle, True, listitem=li)

    def addLink(self, title, mode):
        self.log("Adding Link: " + str(title) + " MODE: " + str(mode))

        media_type = "episode"
        name = title.find('title').text.encode('utf-8')

        original_name = title.find('clearleap:analyticsLabel', namespaces=self.NAMESPACES).text.encode('utf-8')
        if self.force_original_names:
            name = original_name

        plot = ""
        try:
            plot = title.find('description').text.encode('utf-8')
        except:
            pass
        season = 0
        episode = 0
        series_name = ""
        try:
            season = int(title.find('clearleap:season', namespaces=self.NAMESPACES).text)
            episode = int(title.find('clearleap:episodeInSeason', namespaces=self.NAMESPACES).text)
            series_name = title.find('clearleap:series', namespaces=self.NAMESPACES).text.encode('utf-8')
        except:
            pass
        if episode == 0:
            media_type = "movie"

        u = self.base_url + "?url=" + urllib.quote_plus(title.find('link').text) + "&mode=" + str(mode) + "&name=" + urllib.quote_plus(name)

        thunb = self.get_thumbnail_url(title)

        liz = xbmcgui.ListItem(name, iconImage=thunb, thumbnailImage=thunb)
        liz.setArt({'thumb': thunb, 'poster': thunb, 'banner': thunb, 'fanart': thunb})
        liz.setInfo(type="Video",
                    infoLabels={"mediatype": media_type, "episode": episode,
                                "season": season,
                                "tvshowtitle": series_name, "plot": plot,
                                "title": name, "originaltitle": original_name})
        liz.addStreamInfo('video', {'width': 1920, 'height': 1080})
        liz.addStreamInfo('video', {'aspect': 1.78, 'codec': 'h264'})
        liz.addStreamInfo('audio', {'codec': 'aac', 'channels': 2})
        liz.setProperty("IsPlayable", "true")
        xbmcplugin.addDirectoryItem(handle=self.handle, url=u, listitem=liz, isFolder=False)

    def addDir(self, item, mode=1):
        self.log("Adding Dir: " + str(item) + " MODE: " + str(mode))

        media_type = "tvshow"

        plot = ""
        try:
            plot = item.find('description').text.encode('utf-8')
        except:
            pass

        u = self.base_url + "?url=" + urllib.quote_plus(item.find('link').text) + "&mode=" + str(
            mode) + "&name=" + item.find('title').text.encode('utf-8')

        series_name = ""
        try:
            series_name = item.find('clearleap:series', namespaces=self.NAMESPACES).text.encode('utf-8')
        except:
            pass

        thumb = self.get_thumbnail_url(item)

        liz = xbmcgui.ListItem(item.find('title').text.encode('utf-8'), iconImage=thumb, thumbnailImage=thumb)
        liz.setArt({'thumb': thumb, 'poster': thumb, 'banner': thumb,
                    'fanart': thumb})
        liz.setInfo(type="Video", infoLabels={"mediatype": media_type,
                                              "tvshowtitle": series_name,
                                              "title": item.find('title').text.encode('utf-8'),
                                              "Plot": plot})
        liz.setProperty('isPlayable', "false")
        xbmcplugin.addDirectoryItem(handle=self.handle, url=u, listitem=liz, isFolder=True)

    def addCat(self, name, url, icon, mode):
        self.log("Adding Cat: " + str(name) + "," + str(url) + "," + str(icon) + " MODE: " + str(mode))
        u = self.base_url + "?url=" + urllib.quote_plus(url) + "&mode=" + str(mode) + "&name=" + urllib.quote_plus(name)
        liz = xbmcgui.ListItem(name, iconImage=icon, thumbnailImage=icon)
        liz.setArt({'fanart': self.resources + "fanart.jpg"})
        liz.setInfo(type="Video", infoLabels={"Title": name})
        liz.setProperty('isPlayable', "false")
        xbmcplugin.addDirectoryItem(handle=self.handle, url=u, listitem=liz, isFolder=True)
