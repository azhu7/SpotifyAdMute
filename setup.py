
from setuptools import setup

setup(
    name='SpotifyAdMute',
    version='1.0.1',
    description='Spotify listener that mutes ads',
    author='@azhu7',
    author_email='alexzhu95@gmail.com',
    url='https://github.com/azhu7/SpotifyAdMute',
    install_requires=[
        'spotipy', 'pycaw',
    ],
    packages=['SpotifyAdMute'])