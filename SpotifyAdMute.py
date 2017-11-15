'''
Author:        Alexander Zhu
Date Created:  11 November, 2017
Description:   A simple Spotify listener that mutes during ads and unmutes during music
'''

from __future__ import print_function
import sys
import os
import logging
import time
import threading

# Spotify API
import spotipy
import Utility

# Volume controller
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

class SpotifyAdMuteException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg

class SpotifyAdMute(object):
    '''
        Example usage:
            username = 'ryan wu'
            spotifyAdMute = SpotifyAdMute(username)
            spotifyAdMute.run()
    '''

    # Spotify playback states
    class State:
        Paused = 1
        Music = 2
        Ad = 3

    # Initialized in init().
    logger = None
    spotify = None
    volume = None

    username = None
    first_name = None
    state = None
    current_track = None
    cv = threading.Condition()
    quit = False

    # Initialize modules
    def __init__(self, app, username):
        self.app = app
        self.username = username
        self._init_logger()
        self._init_spotify()
        self._init_volume()

        self.first_name = self.spotify.current_user()['display_name'].split()[0]

        self.logger.info('SpotifyAdMute: Successful initialization.')

    # Initialize logger
    def _init_logger(self):
        self.logger = logging.getLogger('SpotifyAdMute')
        current_time = time.strftime('%Y_%m_%d_%H_%M_%S', time.gmtime())
        log_folder = os.path.dirname(os.path.realpath(__file__)) + '/.tmp'
        if not os.path.exists(log_folder):
            os.makedirs(log_folder)

        hdlr = logging.FileHandler('{0}/{1}.log'.format(log_folder, current_time))
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        hdlr.setFormatter(formatter)
        self.logger.addHandler(hdlr)
        self.logger.setLevel(logging.INFO)
        self.logger.info('SpotifyAdMute: Initialized logger.')
        
    # Initialize Spotify
    def _init_spotify(self):
        scope = 'user-read-currently-playing'
        client_id = '56bfb83b714a4c708faef8e06bf7abcb'
        client_secret = '38b7264e4ea04523a7092a01d26081f8'
        redirect_uri = 'http://google.com'
        
        try:
            token = Utility.get_user_token(self.app, self.username, scope, client_id, client_secret, redirect_uri)
        except spotipy.oauth2.SpotifyOauthError as err:
            self.logger.error('SpotifyAdMute: While initializing Spotify, got exception: {0}'.format(str(err)))
            raise SpotifyAdMuteException('Could not verify username: {0}. Make sure you enter the same username as that of the logged-in account.'.format(self.username))
        
        if not token:
            raise SpotifyAdMuteException('Can\'t get token for ' + self.username)

        self.spotify = spotipy.Spotify(auth=token)
        self.logger.info('SpotifyAdMute: Initialized Spotify.')

    # Initialize volume
    def _init_volume(self):
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        self.volume = cast(interface, POINTER(IAudioEndpointVolume))
        self.logger.info('SpotifyAdMute: Initialized volume.')

    # Poll Spotify for information on currently playing track.
    def _try_get_currently_playing(self, retry_attempts=5):
        results = None
        success = False
        while retry_attempts > 0 and not success:
            try:
                results = self.spotify._get('me/player/currently-playing')
                success = True
            except spotipy.client.SpotifyException as err:
                retry_attempts -= 1
                init_spotify(self.username)
                self.logger.error('SpotifyAdMute: While polling for currently playing track information, got exception {0}'.format(str(err)))
            except:
                retry_attempts -= 1
                self.logger.error('SpotifyAdMute: While polling for currently playing track information, got unexpected exception!')

        return results, success

    # Continually poll Spotify for information on currently playing track until successful or user exits.
    def _get_currently_playing(self):
        success = False
        while not success:
            results, success = self._try_get_currently_playing()
            if not success:
                self.logger.error('SpotifyAdMute: Could not poll for currently playing track information. Waiting for user input.')
                response = self.app.ask_user_yesno('Error', 'Could not poll for currently playing track information. Check {0} for more info.\n\n\tTry again?'.format(self.logger.handlers[0].baseFilename))
                done = False
                while not done:
                    if response:
                        done = True
                    else:
                        self.app.stop_ad_mute()
                        self.quit = True
                        return results

        return results

    # Print track information.
    def _print_track(self, item):
        return '"{0}" by {1}'.format(item['name'], item['artists'][0]['name'])

    # Compute remaining time.
    def _get_sleep_duration(self, results):
        if not results or not results['item']:
            return 4  # Sleep for 3 seconds if playing ad

        # Sleep for 10 seconds by default, or less if a track is about to end
        # We poll regularly in case the user skips a track and enters an ad
        # Add 1s to ensure we poll after ad begins
        remaining_duration = (results['item']['duration_ms'] - results['progress_ms']) / 1000 + 1
        return min([remaining_duration, 10])
        
    def _protected_set_mute(self, mute):
        try:
            self.volume.SetMute(mute, None)
        except _ctypes.COMError as err:
            self.logger.error('SpotifyAdMute: While setting mute, got exception: ' + err)
            raise SpotifyAdMuteException('Got an unexpected error. Check {0} for more info.'.format(self.logger.handlers[0].baseFilename))

    # Run main loop that adjusts volume based on current track.
    def poll(self):
        results = self._get_currently_playing()

        if self.quit:
            print("Exiting poll", file=sys.stderr)
            self.quit = False
            return

        if not results or not results['is_playing']:
            # Paused state
            if self.state != self.State.Paused:
                self.state = self.State.Paused
                print('Not playing music. No action taken.')
                self.logger.info('SpotifyAdMute: Not playing music. No action taken.')
        elif results['item']:
            # Music state
            self._protected_set_mute(0)
            if self.current_track != results['item']['name'] or self.state != self.State.Music:
                self.state = self.State.Music
                self.current_track = results['item']['name']
                message = 'Currently playing {0}'.format(self._print_track(results['item']))
                print(message)
                self.logger.info('SpotifyAdMute: {0}'.format(message))
        elif not results['item']:
            # Ad state
            self._protected_set_mute(1)
            if self.state != self.State.Ad:
                self.state = self.State.Ad
                message = 'Playing ad. Muting!'
                print(message)
                self.logger.info('SpotifyAdMute: {0}'.format(message))

        duration = self._get_sleep_duration(results)
        self.cv.acquire()
        self.cv.wait(timeout=duration)
        self.cv.release()

    def stop_poll(self):
        self.cv.acquire()
        self.cv.notify()
        self.cv.release()