'''
Author:        Alexander Zhu
Date Created:  13 November, 2017
Description:   Utility for Spotify Ad Mute
'''

import os
import spotipy.oauth2 as oauth2

import logging
from threading import Timer
import webbrowser

def get_user_token(logger, app, username, scope, client_id, client_secret, redirect_uri, cache_path):
    sp_oauth = oauth2.SpotifyOAuth(client_id, client_secret, redirect_uri, scope=scope, cache_path=cache_path)
    logger.info('Utility: Successfully initialized SpotifyOAuth')

    token_info = sp_oauth.get_cached_token()

    if not token_info:
        logger.info('Utility: Did not find cached token.')
        auth_url = sp_oauth.get_authorize_url()

        try:
            message = "Opened\n%s\nin your browser" % auth_url
        except:
            message = "Please navigate here: %s" % auth_url

        t = Timer(3, webbrowser.open, ['%s' % auth_url])
        t.start()
        response = app.prompt_user(
            'Authentication Required',
            '''User authentication requires interaction with your web browser.
            Once you enter your credentials and give authorization, you will be redirected to a url. Paste that url you were directed to to complete the authorization.
            \n%s\n\nEnter the URL you were redirected to:''' % message)

        t.cancel()  # Cancel timer in case user quit prompt early

        try:
            code = sp_oauth.parse_response_code(response)
            token_info = sp_oauth.get_access_token(code)
        except:
            logger.warn('Utility: Got an exception while getting token. Returning None.')
            return None

    # Auth'ed API request
    if token_info:
        logger.info('Utility: Successfully got token. Returning access token.')
        return token_info['access_token']
    else:
        logger.warn('Utility: Could not get token. Returning None.')
        return None