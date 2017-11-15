from __future__ import print_function

import sys
import os
import threading
from tkinter import *
import tkinter.messagebox
from SpotifyAdMute import SpotifyAdMute, SpotifyAdMuteException

exit_thread = False
exit_success = False

''' TODO
Make output text read-only
Init logger in App, pass into spotify ad mute, which passes into utility
Change text output format to %
'''

# Center tkinter window on screen
def center(root, height, width):
    # Get screen width and height
    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()

    # Calculate x and y coordinates for the Tk root window
    x = (ws/2) - (width/2)
    y = (hs/2) - (height/2)

    # Set the dimensions of the screen and where it is placed
    root.geometry('%dx%d+%d+%d' % (width, height, x, y))

class EntryWindow(object):
    value = None

    def __init__(self, master, title, message):
        self.top = Toplevel(master, pady=20)
        center(self.top, 370, 600)
        self.top.title(title)
        
        # Initialize widgets
        self.message = Label(self.top, text=message, width=60, wraplength=510, padx=20, font=("Trebuchet MS", 12))
        self.message.grid(row=0, column=0)
        self.entry = Entry(self.top, width=40)
        self.entry.grid(row=1, column=0)
        self.submit = Button(self.top, text='Submit', command=self._cleanup)
        self.submit.grid(row=2, column=0)

    def _cleanup(self):
        self.value = self.entry.get()
        self.top.destroy()

class Job(threading.Thread):
    def __init__(self, target):
        threading.Thread.__init__(self)
        self.target = target
        self.shutdown_flag = threading.Event()

    def run(self):
        print('Thread %d started.' % (self.ident), file=sys.stderr)
        while not self.shutdown_flag.is_set():
            print('Thread {0} start run'.format(self.ident), file=sys.stderr)
            self.target()
            print('Thread {0} stop run'.format(self.ident), file=sys.stderr)
 
        # ... Clean shutdown code here ...
        print('Thread {0} stopped.'.format(self.ident), file=sys.stderr)

class App(object):
    run_thread = None

    def __init__(self, master):
        self.master = master
        self.master.protocol('WM_DELETE_WINDOW', self._cleanup)  # Use our own cleanup logic
        self.master.title("Spotify Ad Mute")

        # Initialize widgets
        self.frame = Frame(self.master)
        self.frame.pack()

        self.quit_button = Button(self.frame, text='QUIT', fg='red', command=self._cleanup)
        self.quit_button.pack(side=LEFT)

        self.username_input = Entry(self.master)
        self.username_input.pack()
        self.username_input.insert(0, 'pungun1234')

        self.login_button = Button(self.frame, text='Log In', command=self._login)
        self.login_button.pack(side=LEFT);

        self.text = Text(self.master, width=65, height=50)
        self.text.pack()
        sys.stdout = StdRedirector(self.text)

    def _cleanup(self):
        if tkinter.messagebox.askyesno("Exit", "Are you sure you want to quit the application?"):
            exit_thread = True
            exit_success = True
            print('Thanks for using Spotify Ad Mute!')
            if self.run_thread:
                self.run_thread.shutdown_flag.set()
                self.spotifyAdMute.stop_poll()
                self.run_thread.join()

            self.frame.quit()
            self.master.destroy()

    def _login(self):
        try:
            username = self.username_input.get()
            self.spotifyAdMute = SpotifyAdMute(self, username)
            self._print_intro(self.spotifyAdMute.first_name)
            self.run_thread = Job(target=self.spotifyAdMute.poll)
            self.run_thread.start()
        except SpotifyAdMuteException as err:
            print('Got exception: {0}'.format(str(err)))

    def prompt_user(self, title, message):
        popup = EntryWindow(self.master, title, message)
        self.master.wait_window(popup.top)
        return popup.value

    def ask_user_yesno(self, title, message):
        return tkinter.messagebox.askyesno(title, message)

    def stop_ad_mute(self):
        if self.run_thread:
            self.run_thread.shutdown_flag.set()

        print('Stopped.')

    # Prints some nice intro text
    def _print_intro(self, first_name):
        print('##############################################################')
        print('')
        print('\tWelcome to Spotify Ad Mute, {0}!'.format(first_name))
        print('')
        print('\tThe app will monitor your Spotify playback and ')
        print('\tadjust the volume accordingly.')
        print('')
        print('##############################################################')
        print('')

class StdRedirector(object):
    def __init__(self, widget):
        self.widget = widget
    def write(self, string):
        if not exit_thread:
            self.widget.insert(END,string)
            self.widget.see(END)
    def flush(self):
        pass

# Run the app
if __name__ == '__main__':
    root = Tk()
    center(root, 500, 500)
    app = App(root)
    root.mainloop()
    sys.exit(0)