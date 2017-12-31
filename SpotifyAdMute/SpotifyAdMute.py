'''
Author:        Alexander Zhu
Date Created:  12 November, 2017
Description:   Spotify Ad Mute: A simple Spotify listener that mutes ads
'''

from __future__ import print_function

import sys
import os
import time
import requests
import logging
import threading
import Queue
from enum import Enum

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
    # Spotify playback states
    class State(Enum):
        Paused = 1
        Music = 2
        Ad = 3

    # Initialized in init().
    logger = None
    spotify = None
    volume = None

    # Cached information
    username = None
    first_name = None
    state = None
    current_track = None

    # To break out of sleep early
    cv = threading.Condition()
    notified = False
    quit = False

    # Default poll sleep times (in seconds)
    ad_default_sleep = 4
    music_default_sleep = 10

    # Initialize modules
    def __init__(self, app, logger):
        self.app = app
        self.logger = logger
        self._init_volume()

        self.logger.info('SpotifyAdMute: Successful initialization.')
        
    # Initialize Spotify
    def _init_spotify(self):
        scope = 'user-read-currently-playing'
        client_id = '56bfb83b714a4c708faef8e06bf7abcb'
        client_secret = '38b7264e4ea04523a7092a01d26081f8'
        redirect_uri = 'http://google.com'
        cache_path = '%s/.cache-%s' % (self.app.cache_folder, self.app.username)

        try:
            token = Utility.get_user_token(self.logger, self.app, self.username, scope, client_id, client_secret, redirect_uri, cache_path)
        except spotipy.oauth2.SpotifyOauthError as err:
            self.logger.error('SpotifyAdMute: While initializing Spotify, got exception: %s' % str(err))
            raise SpotifyAdMuteException('Error retrieving token for: %s' % self.username)
        
        if not token:
            self.logger.error('SpotifyAdMute: Got token <None> for %s' % self.username)
            raise SpotifyAdMuteException('Could not get token for %s' % self.username)

        self.spotify = spotipy.Spotify(auth=token)

        try:
            if self.spotify.current_user()['id'] != self.username:
                os.remove(cache_path)  # Remove the mismatched token
                raise SpotifyAdMuteException('Could not verify username: %s. Make sure you enter the same username as that of the logged-in account.' % self.username)
        except requests.ConnectionError as err:
            raise SpotifyAdMuteException('Failed to establish a connection to Spotify. Make sure you are connected to wifi.')
        except:
            raise SpotifyAdMuteException('Got an unknown error while querying from Spotify')

        self.logger.info('SpotifyAdMute: Initialized Spotify.')

    # Initialize volume
    def _init_volume(self):
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        self.volume = cast(interface, POINTER(IAudioEndpointVolume))
        self.logger.info('SpotifyAdMute: Initialized volume.')

    # Poll Spotify for information on currently playing track.
    def _try_get_currently_playing(self, retry_attempts=3):
        results = None
        success = False
        duration = 0.5  # Seconds to wait
        while retry_attempts > 0 and not success:
            try:
                self.logger.info('Querying Spotify.')
                results = self.spotify._get('me/player/currently-playing')
                self.logger.info('Queried Spotify.')
                success = True
            except spotipy.client.SpotifyException as err:
                # TODO: Try manually raising this error and seeing what happens
                self.logger.error('SpotifyAdMute: While polling for currently playing track information, got exception %s' % str(err))
                retry_attempts -= 1
                self._init_spotify()
            except:
                self.logger.error('SpotifyAdMute: While polling for currently playing track information, got unexpected exception!')
                retry_attempts -= 1

            if not success:
                self.logger.info('Printing')
                print('Could not poll Spotify. Retrying in %d seconds' % duration)
                self.logger.info('SpotifyAdMute: Waiting for %d seconds before retrying poll.' % duration)
                self.cv.acquire()
                self.cv.wait(timeout=duration)
                self.cv.release()

                if self.notified:
                    self.logger.info('SpotifyAdMute: Poll was manually interrupted.')
                    self.notified = False
                    self.quit = True  # Quit when we return to poll()
                    return results, True  # Exit waiting loop immediately

                duration *= 2  # Exponentially increase waiting time

        return results, success

    # Continually poll Spotify for information on currently playing track until successful or user exits.
    def _get_currently_playing(self):
        success = False
        while not success:
            results, success = self._try_get_currently_playing()

            if not success:
                self.logger.error('SpotifyAdMute: Could not poll for currently playing track information. Waiting for user input.')
                response_queue = Queue.Queue()
                self.app.request(self.app.ask_user_yesno, ('Error', 'Could not poll for currently playing track information. Check %s for more info.\n\n\tTry again?' % self.logger.handlers[0].baseFilename), response_queue)
                response = response_queue.get()
                done = False
                while not done:
                    if response:
                        done = True
                    else:
                        self.app.request(self.app.stop_ad_mute, None, None)
                        self.quit = True  # Quit when we return to poll()
                        self.logger.info('SpotifyAdMute: User said to stop polling. Sleeping until stop_ad_mute request is serviced by Gui.')
                        self.cv.acquire()
                        self.cv.wait()
                        self.cv.release()

                        if self.notified:
                            self.logger.info('SpotifyAdMute: Indeed, we broke out of the wait with the stop_poll function.')
                            self.notified = False
                        else:
                            self.logger.warn('SpotifyAdMute: Woke up from something else signalling cv?')

                        self.logger.info('SpotifyAdMute: stop_ad_mute request was serviced. Stopping ad mute now.')
                        return results

        return results

    # Print track information.
    def print_current_track(self):
        return '"%s" by %s' % (self.current_track['name'], self.current_track['artists'][0]['name'])

    # Compute remaining time.
    def _get_sleep_duration(self, results):
        if not results or not results['item']:
            return self.ad_default_sleep  # Sleep for 4 seconds if playing ad

        # Sleep for 10 seconds by default, or less if a track is about to end
        # We poll regularly in case the user skips a track and enters an ad
        # Add 1s to ensure we poll after ad begins
        remaining_duration = (results['item']['duration_ms'] - results['progress_ms']) / 1000 + 1
        return min([remaining_duration, self.music_default_sleep])
        
    def _protected_set_mute(self, mute):
        try:
            self.volume.SetMute(mute, None)
        except _ctypes.COMError as err:
            self.logger.error('SpotifyAdMute: While setting mute, got exception: ' + err)
            raise SpotifyAdMuteException('SpotifyAdMute: Got an unexpected error. Check %s for more info.' % self.logger.handlers[0].baseFilename)

    # Run main loop that adjusts volume based on current track.
    def poll(self):
        if not self.spotify:
            raise SpotifyAdMuteException('SpotifyAdMute: Cannot poll because not logged in!')

        self.logger.info('SpotifyAdMute: Begin polling.')

        results = self._get_currently_playing()

        # Quit if user chose to quit during _get_currently_playing()
        if self.quit:
            self.logger.info('SpotifyAdMute: Exiting poll')
            self.quit = False
            return

        # Process results
        if not results or not results['is_playing']:
            self.logger.info('SpotifyAdMute: Entering paused state. Current track: {%s}. Current state: {%s}.' %(self.current_track, self.state))
            # Paused state
            if self.state != self.State.Paused:
                self.state = self.State.Paused
                self.current_track = None
                print('Not playing music. No action taken.')
                self.logger.info('SpotifyAdMute: Not playing music. No action taken.')
                self.app.request(self.app.set_currently_playing_label, None, None)
        elif results['item']:
            self.logger.info('SpotifyAdMute: Entering music state. Current track: {%s}. Current state: {%s}.' %(self.current_track, self.state))
            # Music state
            self._protected_set_mute(0)
            if (self.current_track != None and self.current_track['name'] != results['item']['name']) or self.state != self.State.Music:
                self.state = self.State.Music
                self.current_track = results['item']
                message = 'Currently playing %s' % self.print_current_track()
                print(message)
                self.logger.info('SpotifyAdMute: %s' % message)
                self.app.request(self.app.set_currently_playing_label, None, None)
        elif not results['item']:
            self.logger.info('SpotifyAdMute: Entering ad state. Current track: {%s}. Current state: {%s}.' %(self.current_track, self.state))
            # Ad state
            self._protected_set_mute(1)
            if self.state != self.State.Ad:
                self.state = self.State.Ad
                self.current_track = None
                message = 'Playing ad. Muting!'
                print(message)
                self.logger.info('SpotifyAdMute: %s' % message)
                self.app.set_currently_playing_label()

        # Sleep until timeout or wakeup from a call to stop_poll()
        duration = self._get_sleep_duration(results)
        self.cv.acquire()
        self.cv.wait(timeout=duration)
        self.cv.release()

        if self.notified:
            self.logger.info('SpotifyAdMute: Poll was manually interrupted.')
            self.notified = False

    def stop_poll(self):
        self.logger.info('SpotifyAdMute: Manually stopping poll.')
        self.cv.acquire()
        self.notified = True
        self.cv.notify()
        self.cv.release()

    def clear_cache(self):
        self.state = None
        self.current_track = None

    # Log in with username
    def login(self, username):
        self.username = username
        self._init_spotify()
        self.logger.info('SpotifyAdMute: Logged in as %s', self.spotify.current_user())

        if self.spotify.current_user()['display_name'] == None:
            self.first_name = self.spotify.current_user()['id']
        else:
            self.first_name = self.spotify.current_user()['display_name'].split()[0]

    # Log out
    def logout(self):
        self.logger.info('SpotifyAdMute: Successfully logged out from %s' % self.username)
        self.username = None
        self.first_name = None
        self.spotify = None