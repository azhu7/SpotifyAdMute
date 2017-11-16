import os
import spotipy.oauth2 as oauth2

def get_user_token(app, username, scope, client_id, client_secret, redirect_uri):
    cache_path = ".cache-" + username
    sp_oauth = oauth2.SpotifyOAuth(client_id, client_secret, redirect_uri, scope=scope, cache_path=cache_path)

    token_info = sp_oauth.get_cached_token()

    if not token_info:
        auth_url = sp_oauth.get_authorize_url()

        try:
            import webbrowser
            webbrowser.open(auth_url)
            message = "Opened\n{0}\nin your browser".format(auth_url)
        except:
            message = "Please navigate here: {0}".format(auth_url)

        response = app.prompt_user(
            'Authentication Required',
            '''User authentication requires interaction with your web browser.
            Once you enter your credentials and give authorization, you will be redirected to a url. Paste that url you were directed to to complete the authorization.
            \n{0}\n\nEnter the URL you were redirected to:'''.format(message))

        try:
            code = sp_oauth.parse_response_code(response)
            token_info = sp_oauth.get_access_token(code)
        except:
            return None

    # Auth'ed API request
    if token_info:
        return token_info['access_token']
    else:
        return None