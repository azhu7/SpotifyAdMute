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
Init logger in App, pass into spotify ad mute, which passes into utility
Change text output format to %
Don't actually need spotify username???
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
            self.target()
 
        print('Thread {0} stopped.'.format(self.ident), file=sys.stderr)

class App(object):
    run_thread = None
    username = None

    def __init__(self, master):
        self.master = master
        self.master.protocol('WM_DELETE_WINDOW', self._cleanup)  # Use our own cleanup logic
        self.master.title("Spotify Ad Mute")

        # Initialize widgets
        self.frame = Frame(self.master)
        self.frame.pack(fill='both', expand=True)

        self.username_label = Label(self.frame, text="Spotify Username:", font=('Trebuchet MS', 11))
        self.username_label.grid(row=0, column=0, sticky=E, padx=10, pady=10)

        self.username_input = Entry(self.frame, font=('Trebuchet MS', 11))
        self.username_input.grid(row=0, column=1, sticky=W)
        #self.username_input.insert(0, 'pungun1234')

        self.username_logged_in = Label(self.frame, font=('Trebuchet MS', 11))
        self.username_logged_in.grid(row=0, columnspan=2, pady=10)
        self.username_logged_in.grid_remove()  # Hide the text until logged in

        self.login_button = Button(self.frame, text='Log In', command=self._login, font=('Trebuchet MS', 11))
        self.login_button.grid(row=0, column=1, sticky=E)

        self.start_button = Button(self.frame, text='Start', command=self._start_ad_mute, font=('Trebuchet MS', 11))
        self.start_button.grid(row=1, columnspan=3)
        self.start_button.grid_remove()  # Hide the button until logged in
        self.frame.grid_rowconfigure(1, minsize=35)

        self.text = Text(self.frame, borderwidth=3, relief='sunken', width=55, height=20, font=('Trebuchet MS', 11), wrap='word', state='disabled')
        self.text.grid(row=2, columnspan=2, sticky=NSEW, padx=2, pady=2)
        sys.stdout = StdRedirector(self.text)

        self.text_scroll = Scrollbar(self.frame, command=self.text.yview)
        self.text_scroll.grid(row=2, column=2, sticky=NSEW)
        self.text.config(yscrollcommand=self.text_scroll.set)

    def _cleanup(self):
        if tkinter.messagebox.askyesno("Exit", "Are you sure you want to quit the application?"):
            exit_thread = True
            exit_success = True
            print('Thanks for using Spotify Ad Mute!')
            if self.run_thread:
                self.run_thread.shutdown_flag.set()
                self.spotify_ad_mute.stop_poll()
                self.run_thread.join()

            self.frame.quit()
            self.master.destroy()

    def _login(self):
        try:
            self.username = self.username_input.get()
            self.spotify_ad_mute = SpotifyAdMute(self)
            self.spotify_ad_mute.login(self.username)
            self._print_intro(self.spotify_ad_mute.first_name)
            
            # Transition to logged-in widgets
            self.username_label.grid_remove()
            self.username_input.grid_remove()
            self.username_logged_in.config(text="Logged in as %s" % self.username)
            self.username_logged_in.grid()
            self.login_button.config(text="Log Out", command=self._logout)
            self.start_button.grid()
            self._start_ad_mute()
        except SpotifyAdMuteException as err:
            tkinter.messagebox.showerror(title="Error", message=err)

    def _logout(self):
        self.stop_ad_mute()

        # Transition to logged-out widgets
        self.username_logged_in.grid_remove()
        self.start_button.grid_remove()
        self.username_label.grid()
        self.username_input.grid()
        self.login_button.config(text="Log In", command=self._login)
        self.spotify_ad_mute.logout()
        print('Logged out.')

    def _start_ad_mute(self):
        print('Started.')
        self.run_thread = Job(target=self.spotify_ad_mute.poll)
        self.run_thread.start()
        self.start_button.config(text='Stop', command=self.stop_ad_mute)

    def prompt_user(self, title, message):
        popup = EntryWindow(self.master, title, message)
        self.master.wait_window(popup.top)
        return popup.value

    def ask_user_yesno(self, title, message):
        return tkinter.messagebox.askyesno(title, message)

    def stop_ad_mute(self):
        if self.run_thread:
            self.run_thread.shutdown_flag.set()
            self.spotify_ad_mute.stop_poll()
            self.spotify_ad_mute.clear_cache()

        self.start_button.config(text='Start', command=self._start_ad_mute)
        print('Stopped.')

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

# Run the app
if __name__ == '__main__':
    root = Tk()
    center(root, 500, 500)
    app = App(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app._cleanup()
