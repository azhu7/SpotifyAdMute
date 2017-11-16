from __future__ import print_function

import sys
import os
import threading
import logging
import time
from tkinter import *
import tkinter.messagebox
import tkinter.font
from SpotifyAdMute import SpotifyAdMute, SpotifyAdMuteException

exit_thread = False
exit_success = False

''' TODO
Enter username, press enter to log in
computer sleep crash program?
'''

# Center tkinter window on screen
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

class EntryWindow(object):
    value = None

    def __init__(self, master, title, message):
        self.top = Toplevel(master, pady=20)
        self.top.title(title)
        
        # Initialize widgets
        self.message = Label(self.top, text=message, width=60, wraplength=510, padx=20, font=('Trebuchet MS', 12))
        self.message.grid(row=0, column=0)
        self.entry = Entry(self.top, width=40)
        self.entry.grid(row=1, column=0)
        self.submit = Button(self.top, text='Submit', command=self._cleanup)
        self.submit.grid(row=2, column=0)

        center(self.top)
        self.top.update()
        center(self.top)

    def _cleanup(self):
        self.value = self.entry.get()
        self.top.destroy()

class Job(threading.Thread):
    def __init__(self, logger, target):
        threading.Thread.__init__(self)
        self.target = target
        self.logger = logger
        self.shutdown_flag = threading.Event()

    def run(self):
        self.logger.info('Job: Thread %d started.' % self.ident)
        while not self.shutdown_flag.is_set():
            self.target()
 
        self.logger.info('Job: Thread %d stopped.' % self.ident)

class App(object):
    run_thread = None
    username = None

    # Initialize the App, creating the logger and widgets.
    def __init__(self, master):
        self._init_logger()

        self.master = master
        self.master.protocol('WM_DELETE_WINDOW', self._cleanup)  # Use our own cleanup logic
        self.master.title('Spotify Ad Mute')
        default_font = tkinter.font.nametofont('TkDefaultFont')
        default_font.configure(size=11, family='Trebuchet MS')
        self.master.option_add('*Font', default_font)  # Default font is Trebuchet MS, size 11

        # Initialize widgets
        self.frame = Frame(self.master)
        self.frame.pack(fill='both', expand=True)

        self.username_label = Label(self.frame, text='Spotify Username:')
        self.username_label.grid(row=0, column=0, sticky=E, padx=10, pady=10)

        self.username_input = Entry(self.frame)
        self.username_input.grid(row=0, column=1, sticky=W)
        #self.username_input.insert(0, 'pungun1234')

        self.username_logged_in = Label(self.frame)
        self.username_logged_in.grid(row=0, columnspan=2, pady=10)
        self.username_logged_in.grid_remove()  # Hide the text until logged in

        self.login_button = Button(self.frame, text='Log In', command=self._login)
        self.login_button.grid(row=0, column=1, sticky=E)

        self.start_button = Button(self.frame, text='Start', command=self._start_ad_mute)
        self.start_button.grid(row=1, columnspan=3)
        self.start_button.grid_remove()  # Hide the button until logged in
        self.frame.grid_rowconfigure(1, minsize=35)

        self.text = Text(self.frame, borderwidth=3, relief='sunken', width=55, height=20, wrap='word', state='disabled')
        self.text.grid(row=2, columnspan=2, sticky=NSEW, padx=2, pady=2)
        sys.stdout = StdRedirector(self.text)

        self.text_scroll = Scrollbar(self.frame, command=self.text.yview)
        self.text_scroll.grid(row=2, column=2, sticky=NSEW)
        self.text.config(yscrollcommand=self.text_scroll.set)

        center(self.master)
        self.master.update()
        center(self.master)

        self.logger.info('Gui: Successfully initialized all widgets.')

    # Cleanup all resources used by app.
    def _cleanup(self):
        if tkinter.messagebox.askyesno('Exit', 'Are you sure you want to quit the application?'):
            self.logger.info('Gui: Cleaning up application.')
            print('Thanks for using Spotify Ad Mute!')
            exit_thread = True
            exit_success = True
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
        log_folder = os.path.dirname(os.path.realpath(__file__)) + '/.tmp'
        if not os.path.exists(log_folder):
            os.makedirs(log_folder)

        hdlr = logging.FileHandler('%s/%s.log' % (log_folder, current_time))
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        hdlr.setFormatter(formatter)
        self.logger.addHandler(hdlr)
        self.logger.setLevel(logging.INFO)
        self.logger.info('Gui: Initialized logger.')

    # Log into Spotify account.
    def _login(self):
        try:
            self.username = self.username_input.get()
            self.spotify_ad_mute = SpotifyAdMute(self, self.logger)

            self.logger.info('Gui: Attempting to login with username: %s.' % self.username)
            self.spotify_ad_mute.login(self.username)
            self._print_intro(self.spotify_ad_mute.first_name)
            
            # Transition to logged-in widgets
            self.username_label.grid_remove()
            self.username_input.grid_remove()
            self.username_logged_in.config(text='Logged in as %s' % self.username)
            self.username_logged_in.grid()
            self.login_button.config(text='Log Out', command=self._logout)
            self.start_button.grid()

            # Start polling
            self._start_ad_mute()

            self.logger.info('Gui: Logged in with username: %s, started polling.' % self.username)
        except SpotifyAdMuteException as err:
            tkinter.messagebox.showerror(title='Error', message=err)

    # Log out from Spotify account. Transitions back to login screen.
    def _logout(self):
        self.stop_ad_mute()
        self.spotify_ad_mute.logout()

        # Transition to logged-out widgets
        self.username_logged_in.grid_remove()
        self.start_button.grid_remove()
        self.username_label.grid()
        self.username_input.grid()
        self.login_button.config(text='Log In', command=self._login)

        print('Logged out.')
        self.logger.info('Gui: Successfully logged out.')

    # Create an entry window to get user input.
    def prompt_user(self, title, message):
        popup = EntryWindow(self.master, title, message)
        self.master.wait_window(popup.top)
        return popup.value

    # Ask the user a yes/no question.
    def ask_user_yesno(self, title, message):
        return tkinter.messagebox.askyesno(title, message)

    # Start polling.
    def _start_ad_mute(self):
        # Start a new thread to poll
        self.run_thread = Job(self.logger, self.spotify_ad_mute.poll)
        self.run_thread.start()

        self.start_button.config(text='Stop Listening', command=self.stop_ad_mute)

        print('Started listening.')
        self.logger.info('Gui: Successfully started ad mute.')

    # Stop polling.
    def stop_ad_mute(self):
        # Kill the polling thread
        if self.run_thread:
            self.run_thread.shutdown_flag.set()
            self.spotify_ad_mute.stop_poll()
            self.spotify_ad_mute.clear_cache()

        self.start_button.config(text='Start Listening', command=self._start_ad_mute)

        print('Stopped listening.')
        self.logger.info('Gui: Successfully stopped ad mute.')

    # Prints some nice intro text
    def _print_intro(self, first_name):
        print('#######################################################')
        print('')
        print('\tWelcome to Spotify Ad Mute, {0}!'.format(first_name))
        print('')
        print('\tThe app will monitor your Spotify playback and ')
        print('\tmute during ads.')
        print('')
        print('#######################################################')
        print('')

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

# Run the app.
if __name__ == '__main__':
    root = Tk()
    app = App(root)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        app._cleanup()