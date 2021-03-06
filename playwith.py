import sys
import xbmc,xbmcaddon,xbmcvfs,xbmcgui
import sqlite3
import datetime
import time
import subprocess
from subprocess import Popen
import re
import os,stat
from vpnapi import VPNAPI


def log(what):
    xbmc.log(repr(what),xbmc.LOGERROR)

ADDON = xbmcaddon.Addon(id='script.tvguide.fullscreen')

channel = sys.argv[1]
start = sys.argv[2]

def adapt_datetime(ts):
    return time.mktime(ts.timetuple())

def convert_datetime(ts):
    try:
        return datetime.datetime.fromtimestamp(float(ts))
    except ValueError:
        return None

def windows():
    if os.name == 'nt':
        return True
    else:
        return False


def android_get_current_appid():
    with open("/proc/%d/cmdline" % os.getpid()) as fp:
        return fp.read().rstrip("\0")



def ffmpeg_location():
    ffmpeg_src = xbmc.translatePath(ADDON.getSetting('autoplaywiths.ffmpeg'))

    if xbmc.getCondVisibility('system.platform.android'):
        ffmpeg_dst = '/data/data/%s/ffmpeg' % android_get_current_appid()

        if (ADDON.getSetting('autoplaywiths.ffmpeg') != ADDON.getSetting('ffmpeg.last')) or (not xbmcvfs.exists(ffmpeg_dst) and ffmpeg_src != ffmpeg_dst):
            xbmcvfs.copy(ffmpeg_src, ffmpeg_dst)
            ADDON.setSetting('ffmpeg.last',ADDON.getSetting('autoplaywiths.ffmpeg'))

        ffmpeg = ffmpeg_dst
    else:
        ffmpeg = ffmpeg_src
    log(ffmpeg)
    if ffmpeg:
        try:
            st = os.stat(ffmpeg)
            if not (st.st_mode & stat.S_IXUSR):
                log(st)
                try:
                    os.chmod(ffmpeg, st.st_mode | stat.S_IXUSR)
                except Exception as e:
                    log(e)
        except Exception as e:
            log(e)
    if xbmcvfs.exists(ffmpeg):
        return ffmpeg
    else:
        xbmcgui.Dialog().notification("TVGF", "ffmpeg exe not found!")


sqlite3.register_adapter(datetime.datetime, adapt_datetime)
sqlite3.register_converter('timestamp', convert_datetime)

ADDON.setSetting('playing.channel',channel)
ADDON.setSetting('playing.start',start)

path = xbmc.translatePath('special://profile/addon_data/script.tvguide.fullscreen/source.db')
try:
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
except Exception as detail:
    xbmc.log("EXCEPTION: (script.tvguide.fullscreen)  %s" % detail, xbmc.LOGERROR)

ffmpeg = ffmpeg_location()
log(ffmpeg)
if ffmpeg:
    folder = ADDON.getSetting('autoplaywiths.folder')
    c = conn.cursor()
    c.execute('SELECT stream_url FROM custom_stream_url WHERE channel=?', [channel])
    row = c.fetchone()
    url = ""
    if row:
        url = row[0]
    if not url:
        quit()
    startDate = datetime.datetime.fromtimestamp(float(start))
    c.execute('SELECT DISTINCT * FROM programs WHERE channel=? AND start_date = ?', [channel,startDate])
    title = ""
    for row in c:
        title = row["title"]
        is_movie = row["is_movie"]
        foldertitle = re.sub("\?",'',title)
        foldertitle = re.sub(":|<>\/",'',foldertitle)
        subfolder = "TVShows"
        if is_movie == 'Movie':
            subfolder = "Movies"
        folder = os.path.join(xbmc.translatePath(folder), subfolder, foldertitle)
        if not xbmcvfs.exists(folder):
            xbmcvfs.mkdirs(folder)
        season = row["season"]
        episode = row["episode"]
        if season and episode:
            title += " S%sE%s" % (season, episode)
        endDate = row["end_date"]
        duration = endDate - startDate
        before = int(ADDON.getSetting('autoplaywiths.before'))
        after = int(ADDON.getSetting('autoplaywiths.after'))
        extra = (before + after) * 60
        #TODO start from now
        seconds = duration.seconds + extra
        if seconds > (3600*4):
            seconds = 3600*4
        break
    if not url.startswith('http'):
        player = xbmc.Player()
        player.play(url)
        count = 30
        url = ""
        while count:
            count = count - 1
            time.sleep(1)
            if player.isPlaying():
                url = player.getPlayingFile()
                break
        time.sleep(1)
        player.stop()
        time.sleep(1)

    # Play with your own preferred player and paths
    if url and title:
        name = "%s - %s - %s" % (re.sub(r"[^\w' ]+", "", channel, flags=re.UNICODE),re.sub(r"[^\w' ]+", "", title, flags=re.UNICODE),time.strftime('%Y-%m-%d %H-%M'))
        #name = re.sub("\?",'',name)
        #name = re.sub(":|<>\/",'',name)
        #name = name.encode("cp1252")
        filename = os.path.join(folder,name+'.ts')
        #seconds = 30

        cmd = [ffmpeg, "-y", "-i", url]
        cmd = cmd + ["-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "300",  "-t", str(seconds), "-c", "copy"]
        cmd = cmd + ['-f', 'mpegts','-']
        log(("start",cmd))

        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=windows())
        video = xbmcvfs.File(filename,'wb')
        while True:
            data = p.stdout.read(1000000)
            if not data:
                break
            video.write(data)
        video.close()

        p.wait()
        log(("done",cmd))

    quit()

script = "special://profile/addon_data/script.tvguide.fullscreen/playwith.py"
if xbmcvfs.exists(script):
    xbmc.executebuiltin('RunScript(%s,%s,%s)' % (script,channel,start))

core = ADDON.getSetting('autoplaywiths.player')
if not core:
    quit()

c = conn.cursor()
c.execute('SELECT stream_url FROM custom_stream_url WHERE channel=?', [channel])
row = c.fetchone()
url = ""
if row:
    url = row[0]
if not url:
    quit()
else:
    if xbmc.getCondVisibility("System.HasAddon(service.vpn.manager)"):
        try:
            if ADDON.getSetting('vpnmgr.connect') == "true":
                vpndefault = False
                if ADDON.getSetting('vpnmgr.default') == "true":
                    vpndefault = True
                api = VPNAPI()
                if url[0:9] == 'plugin://':
                    api.filterAndSwitch(url, 0, vpndefault, True)
                else:
                    if vpndefault: api.defaultVPN(True)
        except:
            pass

xbmc.executebuiltin('PlayWith(%s)' % core)
xbmc.executebuiltin('PlayMedia(%s)' % url)