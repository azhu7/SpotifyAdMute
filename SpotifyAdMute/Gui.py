'''
Author:        Alexander Zhu
Date Created:  13 November, 2017
Description:   Gui for Spotify Ad Mute
'''

from __future__ import print_function

import sys
import os
import threading
import logging
import time
from Tkinter import *
import tkMessageBox
import tkFont
from PIL import ImageTk, Image
from SpotifyAdMute import SpotifyAdMute, SpotifyAdMuteException
import Queue
from enum import Enum

exit_thread = False
exit_success = False

''' TODO
bug: entrywindow should spawn centered respective to main window
todo: try manually raising exception in SpotifyAdMute::_try_get_currently_playing()
feature: file menu -> about, submit feedback
feature: remove logs older than 30 days
feature: make url part more intuitive...have a welcome box and have them click to progress.
feature: check for updates
feature: make hide/show details button prettier
feature: open window at location prior to previous close?
'''

# Redirect from output stream to a text widget.
class StdRedirector(object):
    def __init__(self, widget):
        self.widget = widget
    def write(self, string):
        if not exit_thread:
            self.widget.configure(state='normal')
            self.widget.insert(END,string)
            self.widget.see(END)
            self.widget.configure(state='disabled')
    def flush(self):
        pass

# Place Tkinter window outside of screen (bottom right)
def hide(root):
    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()
    root.geometry('+%d+%d' % (ws, hs))

# Center Tkinter window on screen
def center(root):
    # Get screen width and height
    w = root.winfo_width()
    h = root.winfo_height()
    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()

    # Calculate x and y coordinates for the Tk root window
    x = (ws/2) - (w/2)
    y = (hs/2) - (h/2)

    # Set the dimensions of the screen and where it is placed
    root.geometry('+%d+%d' % (x, y))

# A customizable window that takes a user string as input.
class EntryWindow(object):
    value = None

    def __init__(self, master, title, message, x, y):
        self.top = Toplevel(master, pady=20)
        self.top.title(title)
        
        # Initialize widgets
        self.message = Label(self.top, text=message, width=60, wraplength=510, padx=20, font=('Trebuchet MS', 12))
        self.message.grid(row=0, column=0)
        self.entry = Entry(self.top, width=40)
        self.entry.grid(row=1, column=0)
        self.entry.bind('<Return>', (lambda event: self._cleanup()))
        self.submit = Button(self.top, text='Submit', command=self._cleanup)
        self.submit.grid(row=2, column=0)

        hide(self.top)
        self.top.update()
        self.top.geometry('+%d+%d' % (x, y))

    def _cleanup(self):
        self.value = self.entry.get()
        self.top.destroy()

# Periodically runs the specified function.
class RepeatingTimer(threading._Timer):
    def run(self):
        while not self.finished.is_set():
            self.function(*self.args, **self.kwargs)
            self.finished.wait(self.interval)

# A thread customized for Spotify Ad Mute.
class Job(threading.Thread):
    def __init__(self, logger, target):
        threading.Thread.__init__(self)
        self.target = target
        self.logger = logger
        self.shutdown_flag = threading.Event()

    def run(self):
        self.logger.info('Job: Thread %d started.' % self.ident)
        while not self.shutdown_flag.is_set():
            try:
                self.target()
            except SpotifyAdMuteException as err:
                self.logger.error('Job: While running target, got exception: %s' % str(err))
                break
            except:
                self.logger.error('Job: While running target, got unexpected exception!')
                break
 
        self.logger.info('Job: Thread %d stopped.' % self.ident)

# Main gui class.
class App(object):
    requests = Queue.Queue()  # Let other threads create widgets by submitting requests

    version = '1.0.7'
    run_thread = None
    username = None
    running_ad_mute = False
    log_folder = '.logs'
    cache_folder = '.data'
    cache_path = '%s/.spotify_ad_mute_cache' % cache_folder
    view = None
    show_details = False

    class View(Enum):
        Login = 0
        Running = 1

    # Initialize the App, creating the logger and widgets.
    def __init__(self, master):
        self._init_logger()

        self.master = master
        hide(self.master)

        self.master.protocol('WM_DELETE_WINDOW', self._cleanup)  # Use our own cleanup logic
        self.master.title('Spotify Ad Mute %s' % self.version)
        default_font = tkFont.nametofont('TkDefaultFont')
        default_font.configure(size=11, family='Trebuchet MS')
        self.master.option_add('*Font', default_font)  # Default font is Trebuchet MS, size 11

        self.master.iconbitmap(default='assets/spotifyadmute_icon.ico')

        # Initialize widgets
        self.frame = Frame(self.master)
        self.frame.pack(fill='both', expand=True)

        self.username_label = Label(self.frame, text='Spotify Username:')
        self.username_label.grid(row=0, column=0, sticky=E, padx=(10, 5), pady=(10, 0))

        self.username_input = Entry(self.frame)
        self.username_input.grid(row=0, column=1, sticky=W, pady=(10, 0))
        self.username_input.bind('<Return>', (lambda event: self._login()))

        # Caching
        if not os.path.isdir(self.cache_folder):
            self.logger.info('Gui: Creating cache_folder at %s' % self.cache_folder)
            os.mkdir(self.cache_folder)
        if os.path.isfile(self.cache_path):
            with open(self.cache_path, 'r') as cache:
                cached_username = cache.readline()
                self.logger.info('Gui: Found cached username: %s.' % cached_username)
                self.username_input.insert(0, cached_username)
        else:
            self.logger.info('Gui: Did not find cache file: %s' % self.cache_path)

        self.username_logged_in_label = Label(self.frame)
        self.username_logged_in_label.grid(row=0, column=1, columnspan=2, pady=(10, 0))

        # Make sure columns are wide enough for labels. Row 1 shows on login page.
        self.frame.grid_columnconfigure(1, minsize=110)
        self.frame.grid_columnconfigure(2, minsize=110)
        self.frame.grid_rowconfigure(1, minsize=35)

        # Load images
        self.music_img = ImageTk.PhotoImage(Image.open('assets/music-50.png'))
        self.pause_img = ImageTk.PhotoImage(Image.open('assets/pause-50.png'))
        self.mute_img = ImageTk.PhotoImage(Image.open('assets/mute-50.png'))
        self.image_label = Label(self.frame)
        self.image_label.grid(row=0, column=0, rowspan=2, padx=(0, 0), pady=(0, 0))

        # Login button
        self.login_button = Button(self.frame, text='Log In', command=self._login)
        self.login_button.grid(row=0, column=2, sticky=E, padx=(20, 10), pady=(10, 0))

        # Logout button
        self.logout_button = Button(self.frame, text='Log Out', command=self._logout)
        self.logout_button.grid(row=0, column=3, sticky=E, padx=(0, 10), pady=(10, 0))

        # Currently playing label
        self.currently_playing_label_text = StringVar()
        self.currently_playing_label = Message(self.frame, width=250, textvariable=self.currently_playing_label_text)
        self.currently_playing_label.grid(row=1, column=1, columnspan=2)

        # Hide/show details button
        self.details_button_text = StringVar()
        self.details_button_text.set('Show details')
        self.details_button = Button(self.frame, textvariable=self.details_button_text, command=self._toggle_details)
        self.details_button.grid(row=2, column=0, sticky=W, padx=(10, 0), pady=(10, 10))

        # On/off monitoring button
        self.monitoring_button_text = StringVar()
        self.monitoring_button_text.set('Start Monitoring')
        self.monitoring_button = Button(self.frame, textvariable=self.monitoring_button_text, command=self._start_ad_mute)
        self.monitoring_button.grid(row=2, column=1, columnspan=2)

        # Details text
        self.text = Text(self.frame, borderwidth=3, relief='sunken', width=50, height=10, wrap='word', state='disabled')
        self.text.grid(row=3, columnspan=4, sticky=NSEW, padx=(5, 0), pady=5)
        sys.stdout = StdRedirector(self.text)

        # Details text scrollbar
        self.text_scroll = Scrollbar(self.frame, command=self.text.yview)
        self.text_scroll.grid(row=3, column=4, sticky=NSEW, pady=10)
        self.text.config(yscrollcommand=self.text_scroll.set)

        # Start at login view
        self._login_view()

        self.master.update()
        center(self.master)

        self._heartbeat()

        self.logger.info('Gui: Successfully initialized all widgets.')

    # Cleanup all resources used by app.
    def _cleanup(self):
        if tkMessageBox.askyesno('Exit', 'Are you sure you want to quit the application?'):
            self.logger.info('Gui: Cleaning up application.')
            print('Thanks for using Spotify Ad Mute!')
            exit_thread = True
            exit_success = True
            self.heartbeat.cancel()
            if self.run_thread:
                self.run_thread.shutdown_flag.set()
                self.spotify_ad_mute.stop_poll()
                self.run_thread.join()

            self.frame.quit()
            self.master.destroy()
            self.logger.info('Gui: Successfully cleaned up application.')

    # Initialize logger
    def _init_logger(self):
        self.logger = logging.getLogger('SpotifyAdMute')
        current_time = time.strftime('%Y_%m_%d_%H_%M_%S', time.gmtime())
        log_folder = os.path.join(os.path.dirname(os.path.realpath(__file__)), self.log_folder)
        if not os.path.exists(log_folder):
            os.makedirs(log_folder)

        hdlr = logging.FileHandler('%s/%s.log' % (log_folder, current_time))
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        hdlr.setFormatter(formatter)
        self.logger.addHandler(hdlr)
        self.logger.setLevel(logging.INFO)
        self.logger.info('Gui: Initialized logger.')

    # Periodically make sure invariants are satisfied
    def _heartbeat(self):
        self.heartbeat = RepeatingTimer(10, self._heartbeat_tick)
        self.heartbeat.start()

    # Heartbeat function
    def _heartbeat_tick(self):
        if self.running_ad_mute and not (self.run_thread and self.run_thread.is_alive()):
            self.stop_ad_mute()

    # Periodically service requests from other threads
    def tk_loop(self):
        try:
            while True:
                func, arg, response_queue = self.requests.get_nowait()
                self.logger.info("Got request: {%s} {%s} {%s}." % (func, arg, response_queue))
                if arg == None:
                    response = func()
                else:
                    response = func(*arg)
                if response_queue:
                    response_queue.put(response)
        except:
            pass

        root.after(1500, self.tk_loop)

    # Add a request to the queue
    def request(self, func, arg, response_queue):
        self.requests.put((func, arg, response_queue))

    # Log into Spotify account.
    def _login(self):
        try:
            # Initialize SpotifyAdMute and log in
            self.username = self.username_input.get()
            self.spotify_ad_mute = SpotifyAdMute(self, self.logger)

            self.logger.info('Gui: Attempting to login with username: %s.' % self.username)
            self.spotify_ad_mute.login(self.username)
            self._cache_username(self.username)
            self.logger.info('Gui: Successfully logged in with username: %s.' % self.username)

            # Transition to logged-in widgets
            self._running_view()

            # Clear text before showing.
            self.text.configure(state='normal')
            self.text.delete(1.0, END)
            self.text.configure(state='disabled')
            self._print_intro()

            # Start polling
            self._start_ad_mute()

            self.logger.info('Gui: Logged in with username: %s, started polling.' % self.username)
        except SpotifyAdMuteException as err:
            tkMessageBox.showerror(title='Error', message=err)

    # Log out from Spotify account. Transitions back to login screen.
    def _logout(self):
        self.stop_ad_mute()
        self.spotify_ad_mute.logout()

        # Transition to logged-out widgets
        self._login_view()
        self.logger.info('Gui: Successfully logged out.')

    # Create an entry window to get user input.
    def prompt_user(self, title, message):
        self.logger.info('Gui: Prompting user with title{%s}, message{%s}.' % (title, message))
        popup = EntryWindow(self.master, title, message, self.master.winfo_x(), self.master.winfo_y())
        self.master.wait_window(popup.top)
        return popup.value

    # Ask the user a yes/no question.
    def ask_user_yesno(self, title, message):
        self.logger.info('Gui: Asking user yes/no question with title{%s}, message{%s}.' % (title, message))
        return tkMessageBox.askyesno(title, message)

    # Start polling.
    def _start_ad_mute(self):
        self.logger.info('Gui: Starting ad mute.')
        self.running_ad_mute = True

        # Start a new thread to poll
        self.run_thread = Job(self.logger, self.spotify_ad_mute.poll)
        self.run_thread.start()

        self.monitoring_button_text.set('Stop Monitoring')
        self.monitoring_button.config(command=self.stop_ad_mute)

        print('Started monitoring.')
        self.logger.info('Gui: Successfully started ad mute.')

    # Stop polling.
    def stop_ad_mute(self):
        self.logger.info('Gui: Stopping ad mute.')
        self.running_ad_mute = False
        self.set_currently_playing_label()

        # Kill the polling thread
        if self.run_thread:
            self.run_thread.shutdown_flag.set()
            self.spotify_ad_mute.stop_poll()
            
        self.spotify_ad_mute.clear_cache()
        self.monitoring_button_text.set('Start Monitoring')
        self.monitoring_button.config(command=self._start_ad_mute)

        print('Stopped monitoring.')
        self.logger.info('Gui: Successfully stopped ad mute.')

    # Switch to the login view.
    def _login_view(self):
        self.logger.info('Gui: Switching to login view.')
        x = self.master.winfo_x()
        y = self.master.winfo_y()

        hide(self.master)
        for child in self.frame.children.values():
            child.grid_remove()

        self.username_label.grid()
        self.username_input.grid()
        self.login_button.grid()

        self.master.update()
        self.username_input.focus_set()  # Focus on username input
        root.geometry('+%d+%d' % (x, y))

        self.view = self.View.Login
        self.logger.info('Gui: Switched to login view.')

    # Switch to the running view.
    def _running_view(self):
        self.logger.info('Gui: Switching to running view.')
        x = self.master.winfo_x()
        y = self.master.winfo_y()
        hide(self.master)
        for child in self.frame.children.values():
            child.grid_remove()

        self.username_logged_in_label.config(text='Logged in as %s' % self.username)
        self.username_logged_in_label.grid()
        self.logout_button.grid()
        self.monitoring_button.grid()
        self.currently_playing_label_text.set('')
        self.currently_playing_label.grid()

        # When switching to running, hide details by default
        self.show_details = False
        self.details_button_text.set('Show details')
        self.details_button.grid()

        self.master.update()
        root.geometry('+%d+%d' % (x, y))

        self.view = self.View.Running
        self.logger.info('Gui: Switched to running view.')

    def set_currently_playing_label(self):
        self.logger.info('Gui: Setting currently playing label.')

        if not self.running_ad_mute:
            self.currently_playing_label_text.set('Monitoring is off.')
            if self.image_label.grid_info():
                self.image_label.grid_remove()
            return

        if self.spotify_ad_mute.state == SpotifyAdMute.State.Music:
            track = self.spotify_ad_mute.print_current_track()
            current_image = self.music_img
        elif self.spotify_ad_mute.state == SpotifyAdMute.State.Ad:
            track = 'an ad'
            current_image = self.music_img
        elif self.spotify_ad_mute.state == SpotifyAdMute.State.Paused:
            track = 'nothing'
            current_image = self.pause_img

        self.image_label.config(image=current_image)
        self.image_label.image = current_image
        if not self.image_label.grid_info():
            self.image_label.grid()

        self.currently_playing_label_text.set('Currently playing %s.' % track)

    def _toggle_details(self):
        self.logger.info('Gui: Toggling details.')
        self.show_details = not self.show_details
        self.logger.info('Gui: Show details? %s' % self.show_details)

        if self.show_details:
            self.details_button_text.set('Hide details')
            self.text.grid()
            self.text.focus_set()  # Focus on text so user can scroll without clicking first
            self.text_scroll.grid()
        else:
            self.details_button_text.set('Show details')
            self.text.grid_remove()
            self.text_scroll.grid_remove()

    # Save username to load on future runs.
    def _cache_username(self, username):
        self.logger.info('Gui: Caching username: %s.' % username)
        file = open(self.cache_path, 'w')
        file.write(username)

    # Prints some nice intro text.
    def _print_intro(self):
        print('##################################################')
        print('')
        print('\tWelcome to Spotify Ad Mute, {0}!'.format(self.spotify_ad_mute.first_name))
        print('')
        print('\tThe app will monitor your Spotify playback')
        print('\tand mute during ads.')
        print('')
        print('##################################################')
        print('')

# Run the app.
if __name__ == '__main__':
    app = None

    try:
        root = Tk()
        app = App(root)
        app.tk_loop()
        root.mainloop()
    except KeyboardInterrupt:
        if app:
            if app.logger:
                app.logger.info('Exiting from keyboard interrupt.')
            app._cleanup()
    except:
        if app:
            if app.logger:
                app.logger.error('Unknown error at main level.')
            app._cleanup()