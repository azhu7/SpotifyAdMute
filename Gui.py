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
Fix quit join thing
'''

class EntryWindow(object):
    value = None

    def __init__(self, master, title, message):
        self.top = Toplevel(master, pady=20)
        self.top.title(title)

        self.message = Label(self.top, text=message, wraplength=510, padx=20, font=("Trebuchet MS", 12))
        self.message.pack()
        self.entry = Entry(self.top, width=40)
        self.entry.pack()
        self.submit = Button(self.top, text='Submit', command=self._cleanup)
        self.submit.pack()

        self.top.geometry("+{0}+{1}".format(500, 400))
    
    def _cleanup(self):
        self.value = self.entry.get()
        self.top.destroy()

class AskWindow(object):
    value = None

    def __init__(self, master, title, message):
        self.top = Toplevel(master)
        self.top.title(title)
        print('Asking', file=sys.stderr)

        self.message = Label(self.top, text=message, wraplength=520, padx=20, pady=20, font=("Trebuchet MS", 12))
        self.message.grid(row=0, column=0, columnspan=2)
        self.yes_button = Button(self.top, text="Yes", width=10, bg="green", command=self._yes)
        self.yes_button.grid(row=1, column=0, sticky=E, padx=10, pady=20)
        self.no_button = Button(self.top, text='No', width=10, bg="red", command=self._no)
        self.no_button.grid(row=1, column=1, sticky=W, padx=10, pady=20)

        self.top.geometry("+{0}+{1}".format(500, 400))

    def _yes(self):
        self.value = True
        self.top.destroy()

    def _no(self):
        self.value = False
        self.top.destroy()
        

class Job(threading.Thread):
    def __init__(self, target):
        threading.Thread.__init__(self)
        self.target = target
        self.shutdown_flag = threading.Event()

    def run(self):
        print('Thread {0} started.'.format(self.ident), file=sys.stderr)
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
        self.master.title("Spotify Ad Mute")
        self.master.geometry('500x500+500+300')

        self.frame = Frame(self.master)
        self.frame.pack()

        self.quit_button = Button(self.frame, text='QUIT', fg='red', command=self._cleanup)
        self.quit_button.pack(side=LEFT)

        self.username_input = Entry(self.master)
        self.username_input.pack()
        self.username_input.insert(0, 'pungun1234')

        self.login_button = Button(self.frame, text='Log In', command=self.login)
        self.login_button.pack(side=LEFT);

        self.text = Text(self.master, width=65, height=50)
        self.text.pack()
        
        sys.stdout = StdRedirector(self.text)

    def _cleanup(self):
        exit_thread = True
        exit_success = True
        print('Thanks for using Spotify Ad Mute!')
        if self.run_thread:
            print('a', file=sys.stderr)
            self.run_thread.shutdown_flag.set()
            print('b', file=sys.stderr)
            self.spotifyAdMute.stop_poll()
            print('c', file=sys.stderr)
            self.run_thread.join()

        self.frame.quit()

    def login(self):
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

    def ask_user(self, title, message):
        print('Making ask window', file=sys.stderr)
        popup = AskWindow(self.master, title, message)
        self.master.wait_window(popup.top)
        return popup.value

    def stop_ad_mute(self):
        if self.run_thread:
            self.run_thread.shutdown_flag.set()

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
    app = App(root)
    root.mainloop()
    root.destroy()
    sys.exit(0)