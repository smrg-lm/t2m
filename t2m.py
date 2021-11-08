
from typing import List
from dataclasses import dataclass, field
from pathlib import Path
import tempfile
import zipfile
import threading
import time
import re
import random
import queue
import logging
import sys
from getpass import getpass

import sc3.all as sc
import yaml
import tweepy
import spacy
import freesound
import ffmpeg
from PySide2 import QtCore, QtGui, QtWidgets #, QtMultimedia, QtMultimediaWidgets
from PySide2.QtCore import QPointF, QSizeF, QRectF
# from PySide6 import QtCore, QtGui, QtWidgets #, QtMultimedia, QtMultimediaWidgets
# from PySide6.QtCore import QPointF, QSizeF, QRectF


# tweets: [
#     Tweet(
#         id: int,
#         user: str,
#         time: float,
#         text: str,
#         words: [
#             Word(
#                 text: str,
#                 index: int,
#                 sound: Sound(
#                     id: int,
#                     path: str,
#                     file_name: str,
#                     user: str
#                 )
#             ),
#             ...
#         ]
#         config: Config(
#             hashtag: str
#             select = List[str]  # Analysis.
#             filter: str  # Freesound.
#         )
#     ),
#     ...
# ]


@dataclass(frozen=True)
class Config():
    hashtag: str
    select: List[str]
    filter: str
    search_wait_time: float
    tweet_dur: float
    credentials: str


@dataclass
class Sound():
    id: int
    path: str
    file_name: str
    user: str


@dataclass
class Word():
    text: str
    index: int
    sound: str = field(default_factory=str)


@dataclass
class Tweet():
    id: int
    user: str
    time: float
    text: str
    config: Config
    words: List[Word] = field(default_factory=list)


class TwitterV1():
    logger = logging.getLogger('Twitter')

    def __init__(self):
        data = load_credentials('twitter_v1.yaml')
        auth = tweepy.OAuthHandler(data['consumer_key'], data['consumer_secret'])
        auth.set_access_token(data['access_token'], data['access_token_secret'])
        self.api = tweepy.API(auth)
        self.since_id = None  # *** Habría que guardarlo en disco por si se usa dos veces el mismo día, podría ir en una llave 'config' de data.

    def query(self, config: Config) -> List[Tweet]:
        search_results = self.api.search_tweets(
            config.hashtag,
            count=3,  # Tweets per search.
            lang='en',
            result_type='recent',  # Search from last days.
            since_id=self.since_id,  # Does not repeat old tweets.
            include_entities=False)

        if len(search_results) > 0:
            self.since_id = search_results.since_id
            self.logger.info('%i new tweets.', len(search_results))
        else:
            self.logger.info('No new tweets found.')

        tweets = []
        for r in reversed(search_results):  # Creation order.
            tweets.append(
                Tweet(
                    id=r.id,
                    user=r.author.screen_name,
                    time=r.created_at.timestamp(),  # UTC time in seconds.
                    text=r.text,
                    words=[],
                    config=config))

        return tweets


class Analysis():
    # nlp = spacy.load('en_core_web_sm')

    def __init__(self):
        self.nlp = spacy.load('en_core_web_sm')
        self.hashtag_pattern = re.compile(r"\#\S+")
        self.link_pattern = re.compile(r"http\S+")
        self.replacement = lambda match: ' ' * len(match.group())

    def process(self, tweets: List[Tweet]) -> None:
        for tweet in tweets:
            text = re.sub(self.hashtag_pattern, self.replacement, tweet.text)
            text = re.sub(self.link_pattern, self.replacement, text)
            doc = self.nlp(text)
            for token in doc:
                if token.pos_ in tweet.config.select:
                    tweet.words.append(Word(text=token.text, index=token.idx))


class FreesoundV2():
    logger = logging.getLogger('Freesound')
    NO_SOUNDS_EXIST = '<no sounds exist>'

    def __init__(self):
        data = load_credentials('freesound_v2.yaml')
        self.client = freesound.FreesoundClient()
        self.client.set_token(data['api_key'])
        self.fields = 'id,name,previews,username,tags,images'
        self.search_cache = dict()  # {word: results}
        self.sound_cache = dict()  # {id: file_name}

    def process(self, tweet: Tweet) -> None:
        for word in tweet.words:
            results = self.search_cache.get(word.text)

            if results == self.NO_SOUNDS_EXIST:
                continue

            if not results:
                results = self.client.text_search(
                    query=word.text,
                    filter=tweet.config.filter,
                    fields=self.fields,
                    page=1, page_size=5)
                if results.count == 0:
                    self.logger.info("No sounds found for '%s'", word.text)
                    self.search_cache[word.text] = self.NO_SOUNDS_EXIST
                    continue
                self.search_cache[word.text] = results

            sound = freesound.Sound(random.choice(results.results), self.client)
            id = sound.id

            if id in self.sound_cache:
                file_name = self.sound_cache[id]
                path = str(Path(SOUNDS_FOLDER) / Path(str(id) + '.wav'))
            else:
                file_name = str(id) + '.mp3'
                sound.retrieve_preview(SOUNDS_FOLDER, file_name)
                p1 = str(Path(SOUNDS_FOLDER) / Path(file_name))
                p2 = str(Path(SOUNDS_FOLDER) / Path(str(id) + '.wav'))
                ffmpeg.input(p1).output(p2).run(quiet=True, overwrite_output=True)
                self.sound_cache[id] = file_name
                path = p2

            word.sound = Sound(
                id=id, path=path, file_name=sound.name, user=sound.username)
            self.logger.info("%s sound selected for '%s'", path, word.text)


class T2M():
    logger = logging.getLogger('T2M')

    def __init__(self, scheduler, config):
        self._thread = None
        self._thread_running = False
        self.twitter = TwitterV1()
        self.freesound = FreesoundV2()
        self.analysis = Analysis()
        self.scheduler = scheduler
        self.config = config

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread_running = True
        self._thread.start()

    def _run(self):
        while self._thread_running:
            time.sleep(self.config.search_wait_time)
            try:
                self.logger.info(f'searching tweets for {self.config.hashtag}...')
                # Get new tweets.
                tweets = self.twitter.query(self.config)
                if len(tweets) == 0:
                    continue

                self.logger.info('analysing data...')
                # Process text data into words.
                self.analysis.process(tweets)
                if not self._thread_running:
                    return

                for tweet in tweets:
                    self.logger.info('freesound search...')
                    # Search for a sound for each word in text data.
                    self.freesound.process(tweet)
                    # Known ERROR:T2M:URLError: <urlopen error EOF occurred in violation of protocol (_ssl.c:1131)>

                    self.logger.info('scheduling tweets...')
                    # Send data for playback.
                    self.scheduler.add_tweet(tweet)
            except Exception as e:
                self.logger.error('%s: %s', type(e).__qualname__, e)

    def stop(self):
        if self._thread is not None:
            self._thread_running = False
            self._thread.join()


class View(QtWidgets.QGraphicsView):
    global_instance = None

    # def __new__(cls):  # Maybe Qt uses this method differently, maybe there is a bug somewere else.
    #     if cls.global_instance is not None:
    #         raise Exception('View object already active')
    #     cls.global_instance = super().__new__(cls)
    #     return cls.global_instance

    def __init__(self):
        if type(self).global_instance is not None:
            raise Exception('View object already active')
        type(self).global_instance = self

        QtWidgets.QGraphicsView.__init__(self)

        scene = QtWidgets.QGraphicsScene(self)
        scene.setItemIndexMethod(QtWidgets.QGraphicsScene.NoIndex)
        self.setScene(scene)

        self.setStyleSheet('border: 0px')
        self.setBackgroundBrush(QtCore.Qt.black)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.FullViewportUpdate)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setMinimumSize(800, 600)
        self.setWindowTitle('T2M')

        # 1 or 2.
        self._scene_pos = QPointF(0, 0)
        self._scene_size = QSizeF(1280, 720)
        self._init_background1()

    def _init_background1(self):
        self.rect_item = QtWidgets.QGraphicsRectItem(QRectF(self._scene_pos, self._scene_size))
        self.rect_item.setPen(QtCore.Qt.NoPen)
        self.rect_item.setBrush(QtCore.Qt.black)
        self.scene().addItem(self.rect_item)
        self.background_item = self.rect_item

    # def _init_background2(self):
    #     # Incomplete, needs a path and load on or more mp4.
    #     self.video_playlist = QtMultimedia.QMediaPlaylist()
    #     self.video_playlist.addMedia(QtCore.QUrl.fromLocalFile('*** PATH ***'))
    #     self.video_playlist.setCurrentIndex(1)
    #     self.video_playlist.setPlaybackMode(QtMultimedia.QMediaPlaylist.Loop)  # { CurrentItemOnce, CurrentItemInLoop, Sequential, Loop, Random }
    #     self.video_player = QtMultimedia.QMediaPlayer()
    #     self.video_player.setMuted(True)
    #     self.video_player.setPlaylist(self.video_playlist)
    #     self.video_item = QtMultimediaWidgets.QGraphicsVideoItem()
    #     self.video_item.setPos(self._scene_pos)
    #     self.video_item.setSize(self._scene_size)
    #     self.video_player.setVideoOutput(self.video_item)
    #     self.scene().addItem(self.video_item)
    #     self.video_player.play()
    #     self.background_item = self.video_item

    def update_view_scale(self):
        self.fitInView(self.background_item.boundingRect(), QtCore.Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        self.update_view_scale()
        super().resizeEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key == QtCore.Qt.Key_Escape:
            self.close()
        elif key == QtCore.Qt.Key_F:
            if self.windowState() != QtCore.Qt.WindowFullScreen:
                self.showFullScreen()
            else:
                self.showNormal()
        else:
            super().keyPressEvent(event)

    @QtCore.Slot()
    def _create_TweetPlayer(self, id, text, dur):
        player = _ViewPlayer(text, dur)
        setattr(self, '__player_' + str(id), player)

    @QtCore.Slot()
    def _play_tweet(self, id):
        getattr(self, '__player_' + str(id)).play()

    @QtCore.Slot()
    def _play_word(self, id, word, dur):
        getattr(self, '__player_' + str(id)).play_word(word, dur)

    @QtCore.Slot()
    def _stop_tweet(self, id):
        getattr(self, '__player_' + str(id)).stop()
        delattr(getattr(self, '__player_' + str(id)))


class GraphicsRoundedRectItem(QtWidgets.QGraphicsRectItem):
    def paint(self, painter, *_):
        rect = self.boundingRect()
        painter.setPen(QtCore.Qt.NoPen)
        # painter.setBrush(QtGui.QColor(0, 0, 0, 255 * 0.5))  # For movies.
        painter.setBrush(QtCore.Qt.black)
        painter.drawRoundedRect(rect, 20, 20)


class _ViewPlayer(QtCore.QObject):
    def __init__(self, text, dur):
        super().__init__()

        self.scene = View.global_instance.scene()

        parent_item = View.global_instance.background_item
        rect = parent_item.boundingRect()
        rect = QRectF(0, 0, rect.width() - 100, rect.height() - 100)
        self.text_background = GraphicsRoundedRectItem(rect, parent_item)
        self.text_background.setPos(50, 50)

        self.tweet_font = QtGui.QFont("Monospace", 22, QtGui.QFont.Bold)
        self.word_font = QtGui.QFont("Monospace", 16, QtGui.QFont.Bold)
        self.text_width = None

        self.text = text
        self.tweet = None
        self.words = []

        self.dur = dur
        self._elapsed_time = 0
        self.timer = None

    def format_text(self, document, font):
        # To render formated text uses to much CPU with movies.
        cursor = QtGui.QTextCursor(document)
        cursor.select(QtGui.QTextCursor.Document)
        format = QtGui.QTextCharFormat()
        format.setForeground(QtCore.Qt.white)
        char_height = QtGui.QFontMetrics(font).height()
        pen = QtGui.QPen(QtCore.Qt.black, char_height * 0.05)
        format.setTextOutline(pen)
        cursor.mergeCharFormat(format)

    @QtCore.Slot()
    def play(self):
        if self.timer is not None:
            return

        self.tweet = QtWidgets.QGraphicsTextItem(self.text, self.text_background)

        rect = self.text_background.boundingRect()
        self.text_width = rect.width() - 50
        self.tweet.setPos(25, 25)

        self.tweet.setFont(self.tweet_font)
        self.tweet.setTextWidth(self.text_width)
        self.tweet.setDefaultTextColor(QtGui.Qt.white)
        # self.format_text(self.tweet.document(), self.tweet_font)

        char_height = QtGui.QFontMetrics(self.tweet_font).height()
        bl = self.tweet.boundingRect().bottomLeft() + QPointF(0, char_height)
        self.next_line_pos = self.tweet.mapToParent(bl)

        self._elapsed_time = 0
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.timerEvent)
        fps = 30
        ms = 1000 / fps
        self._T = ms * 0.001
        self.timer.start(ms)

    def timerEvent(self):
        self._elapsed_time += self._T
        if self._elapsed_time >= self.dur:
            self.stop()
            self.timer.stop()
            self.timer = None
            return
        for word in self.words[:]:
            if self._elapsed_time >= word.dur:
                if word in self.scene.items():
                    self.scene.removeItem(word)
                    self.words.remove(word)

    @QtCore.Slot(str, float)
    def play_word(self, word, dur):
        if self.timer is None:
            return

        text = word.text + ' : ' + Path(word.sound.file_name).stem + ' | ' + word.sound.user

        word_item = QtWidgets.QGraphicsTextItem(text, self.text_background)
        word_item.setPos(self.next_line_pos)
        word_item.setFont(self.word_font)
        word_item.setTextWidth(self.text_width)
        word_item.setDefaultTextColor(QtGui.Qt.white)
        # self.format_text(word_item.document(), self.word_font)

        word_item.dur = self._elapsed_time + dur
        self.words.append(word_item)
        bl = word_item.boundingRect().bottomLeft()
        self.next_line_pos = word_item.mapToParent(bl)

    @QtCore.Slot()
    def stop(self):
        self.scene.removeItem(self.text_background)
        self.words = []


class TweetPlayer(QtCore.QObject):
    _object_id = 0
    _create_signal = QtCore.Signal(int, str, float)
    _play_signal = QtCore.Signal(int)
    _word_signal = QtCore.Signal(int, object, float)
    _stop_signal = QtCore.Signal(int)

    def __init__(self, text, dur):
        if not View.global_instance:
            raise Exception('View not initialized')
        super().__init__()
        self._id = type(self)._object_id
        type(self)._object_id += 1
        global_view = View.global_instance

        self._create_signal.connect(global_view._create_TweetPlayer)
        self._create_signal.emit(self._id, text, dur)

        self._play_signal.connect(global_view._play_tweet)
        self._word_signal.connect(global_view._play_word)
        self._stop_signal.connect(global_view._stop_tweet)

    def play(self):
        self._play_signal.emit(self._id)

    def play_word(self, word, dur):
        self._word_signal.emit(self._id, word, dur)

    def stop(self):
        self._stop_signal.emit(self._id)


class SoundPlayer():
    # logger = logging.getLogger('SoundPlayer')
    def_prefix = 'word_player_'

    def __init__(self, word: Word, amp=0.2, dur=1, fadein=5, fadeout=5,
                 target=None):
        self.word = word
        self.amp = amp
        self.dur = dur
        self.fadein = fadein
        self.fadeout = fadeout
        self.target = target

    def play(self):
        def action(buf):
            synth = sc.Synth(
                self.def_prefix + str(buf.channels),
                [
                    'buf', buf,
                    'amp', self.amp,
                    'dur', self.dur,
                    'fadein', self.fadein,
                    'fadeout', self.fadeout
                ],
                target=self.target
            )
            synth.on_free(lambda: buf.free())

        path = str(Path(self.word.sound.path).absolute())
        sc.Buffer.new_read(path, action=action)

    # Falta nodo con limitador + HPF.
    @classmethod
    def build_def(cls, channels):
        def func(out, buf, amp=0.2, dur=1, fadein=5, fadeout=5):
            src = sc.ChannelList([
                sc.PlayBuf.ar(
                    channels=channels,
                    bufnum=buf,
                    rate=sc.BufRateScale.kr(buf),
                    start_pos=sc.Rand(0, sc.BufFrames.kr(buf)),
                    loop=True
                )
            for _ in range(4)])

            if channels == 2:
                src2 = src.sum() * 0.5
            else:
                src2 = src

            src2 = sc.GrainIn.ar(
                channels=2,
                trigger=sc.Dust.kr(sc.LFNoise1.kr(0.5).range(2, 20)),
                dur=sc.LFNoise2.kr(0.5).range(0.01, 1),
                input=src2,
                pan=sc.LFNoise2.kr(1) * 0.75,
            ) * 0.5  # HARDCODED

            env = sc.EnvGen.kr(
                env=sc.Env.linen(fadein, dur - fadein - fadeout, fadeout),
                done_action=2
            )

            snd = (src + src2) * env * amp
            sc.Out.ar(out, snd)

        sc.SynthDef(cls.def_prefix + str(channels), func).add()


class Scheduler():
    def __init__(self, config):
        self._wait_time = 0.5
        self._thread = None
        self._thread_running = False
        self.config = config
        self.queue = queue.Queue()

    def add_tweet(self, tweet):
        self.queue.put(tweet)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread_running = True
        self._thread.start()

    def _run(self):
        while self._thread_running:
            while self.queue.empty():
                time.sleep(self._wait_time)

            while not self.queue.empty():
                tweet_dur = self.config.tweet_dur
                tweet = self.queue.get()
                words = [w for w in tweet.words if w.sound]

                if words:
                    # Show tweet text.
                    tweet_player = TweetPlayer(tweet.user + ' | ' + tweet.text, tweet_dur)
                    tweet_player.play()

                    n_words = len(words)
                    hop_dur = tweet_dur / n_words / 2
                    word_dur = tweet_dur - hop_dur * (n_words - 1)

                    for word in words:
                        # text, index, sound
                        # Show selected word.
                        tweet_player.play_word(word, word_dur)
                        # Play word sound.
                        SoundPlayer(word, dur=word_dur).play()
                        # Wait time between words.
                        time.sleep(hop_dur)

                    time.sleep(tweet_dur - hop_dur * n_words)
                else:
                    tweet_dur = 10  # Silent tweet.
                    # Show tweet text.
                    tweet_player = TweetPlayer(tweet.user + ' | ' + tweet.text, tweet_dur)
                    tweet_player.play()
                    tweet_player.play_word('No sounds found for this tweet', tweet_dur)
                    time.sleep(tweet_dur)

    def stop(self):
        if self._thread is not None:
            self._thread_running = False
            self._thread.join()


def load_config():
    with open('config.yaml', 'r') as file:
        return Config(**yaml.safe_load(file.read()))


def load_credentials(file_name):
    if not len(PASSWORD):
        with open(file_name, 'r') as file:
            return yaml.safe_load(file.read())
    else:
        with zipfile.ZipFile(CREDENTIALS_FILE) as zf:
            with zf.open(file_name, pwd=bytes(PASSWORD, 'utf8')) as file:
                return yaml.safe_load(file.read())


if __name__ == '__main__':
    config = load_config()
    CREDENTIALS_FILE = config.credentials
    PASSWORD = getpass()
    SOUNDS_FOLDER = Path(tempfile.gettempdir()) / 't2m_sounds'
    if not SOUNDS_FOLDER.exists():
        SOUNDS_FOLDER.mkdir()

    # Init SuperCollider.
    sc.s.boot()
    SoundPlayer.build_def(1)
    SoundPlayer.build_def(2)

    # Init Qt.
    app = QtWidgets.QApplication(sys.argv)
    view = View()

    # Init Scheduler.
    scheduler = Scheduler(config)
    scheduler.start()

    # Init T2M
    t2m = T2M(scheduler, config)
    t2m.start()

    # Start Qt App.
    view.show()
    sys.exit(app.exec_())
