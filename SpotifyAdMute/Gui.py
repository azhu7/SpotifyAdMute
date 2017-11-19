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
from queue import Queue

exit_thread = False
exit_success = False

''' TODO
file menu -> about, submit feedback
login screen
'''


# Place tkinter window outside of screen (bottom right)
def hide(root):
    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()
    root.geometry('+%d+%d' % (ws, hs))

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
        self.entry.bind('<Return>', (lambda event: self._cleanup()))
        self.submit = Button(self.top, text='Submit', command=self._cleanup)
        self.submit.grid(row=2, column=0)

        hide(self.top)
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
    requests = Queue()  # Let other threads create widgets

    run_thread = None
    username = None

    # Initialize the App, creating the logger and widgets.
    def __init__(self, master):
        self._init_logger()

        self.master = master
        hide(self.master)

        self.master.protocol('WM_DELETE_WINDOW', self._cleanup)  # Use our own cleanup logic
        self.master.title('Spotify Ad Mute')
        default_font = tkinter.font.nametofont('TkDefaultFont')
        default_font.configure(size=11, family='Trebuchet MS')
        self.master.option_add('*Font', default_font)  # Default font is Trebuchet MS, size 11

        # Initialize widgets
        self.frame = Frame(self.master)
        self.frame.pack(fill='both', expand=True)

        self.username_label = Label(self.frame, text='Spotify Username:')
        self.username_label.grid(row=0, column=0, sticky=E, padx=(10, 5), pady=(10, 0))

        self.username_input = Entry(self.frame)
        self.username_input.grid(row=0, column=1, sticky=W, pady=(10, 0))
        self.username_input.bind('<Return>', (lambda event: self._login()))
        self.username_input.insert(0, 'pungun1234')

        self.username_logged_in_label = Label(self.frame)
        self.username_logged_in_label.grid(row=0, columnspan=2, pady=(5, 0))

        self.login_button = Button(self.frame, text='Log In', command=self._login)
        self.login_button.grid(row=0, column=2, sticky=E, padx=(20, 10), pady=(10, 0))

        self.logout_button = Button(self.frame, text='Log Out', command=self._logout)
        self.logout_button.grid(row=0, column=1, columnspan=2, sticky=E, padx=(0, 10), pady=(10, 0))

        self.start_button = Button(self.frame, text='Start Monitoring', command=self._start_ad_mute)
        self.start_button.grid(row=1, columnspan=3)
        self.frame.grid_rowconfigure(1, minsize=35)

        self.text = Text(self.frame, borderwidth=3, relief='sunken', width=55, height=20, wrap='word', state='disabled')
        self.text.grid(row=2, columnspan=2, sticky=NSEW, padx=(5, 0), pady=5)
        sys.stdout = StdRedirector(self.text)

        self.text_scroll = Scrollbar(self.frame, command=self.text.yview)
        self.text_scroll.grid(row=2, column=2, sticky=NSEW, pady=10)
        self.text.config(yscrollcommand=self.text_scroll.set)

        # Start at login view
        self._login_view()

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

    # Periodically service requests from other threads
    def tk_loop(self):
        try:
            while True:
                func, arg, response_queue = self.requests.get_nowait()
                response = func(*arg)
                if response_queue: response_queue.put(response)
        except:
            pass

        root.after(1500, self.tk_loop)

    # Add a request to the queue
    def request(self, func, arg, response_queue):
        self.requests.put((func, arg, response_queue))

    # Log into Spotify account.
    def _login(self):
        try:
            self.username = self.username_input.get()
            self.spotify_ad_mute = SpotifyAdMute(self, self.logger)

            self.logger.info('Gui: Attempting to login with username: %s.' % self.username)
            self.spotify_ad_mute.login(self.username)
            self.logger.info('Gui: Successfully logged in with username: %s.' % self.username)
            
            # Transition to logged-in widgets
            self._running_view()

            self._print_intro(self.spotify_ad_mute.first_name)

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
        self._login_view()

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

        self.start_button.config(text='Stop Monitoring', command=self.stop_ad_mute)

        print('Started monitoring.')
        self.logger.info('Gui: Successfully started ad mute.')

    # Stop polling.
    def stop_ad_mute(self):
        # Kill the polling thread
        if self.run_thread:
            self.run_thread.shutdown_flag.set()
            self.spotify_ad_mute.stop_poll()
            self.spotify_ad_mute.clear_cache()

        self.start_button.config(text='Start Monitoring', command=self._start_ad_mute)

        print('Stopped monitoring.')
        self.logger.info('Gui: Successfully stopped ad mute.')

    def _login_view(self):
        self.logger.info('Gui: Switching to login view.')
        hide(self.master)
        for child in self.frame.children.values():
            child.grid_remove()

        self.username_label.grid()
        self.username_input.grid()
        self.login_button.grid()
        self.master.update()
        center(self.master)
        self.logger.info('Gui: Switched to login view.')

    def _running_view(self):
        self.logger.info('Gui: Switching to running view.')
        hide(self.master)
        for child in self.frame.children.values():
            child.grid_remove()

        self.username_logged_in_label.config(text='Logged in as %s' % self.username)
        self.username_logged_in_label.grid()
        self.logout_button.grid()
        self.start_button.grid()

        # Clear text before showing
        self.text.configure(state='normal')
        self.text.delete(1.0, END)
        self.text.configure(state='disabled')
        self.text.grid()
        self.text_scroll.grid()

        self.master.update()
        center(self.master)
        self.logger.info('Gui: Switched to running view.')

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
    app.tk_loop()

    try:
        root.mainloop()
    except KeyboardInterrupt:
        app._cleanup()