import socket
import time
import tkinter as tk
from tkinter import ttk, messagebox
import re
from threading import Thread, Lock, Event, current_thread
import subprocess
import os
import json
import logging
import sys
import queue
import requests


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


UDP_TIMEOUT = 15.0
FAVORITES_FILE = 'favorites.json'
LOCAL_SERVER_LIST_FILE = 'eu-sv.txt'
SERVERS_CACHE_FILE = 'servers_cache.json'
SETTINGS_FILE = 'settings.json'


PING_THRESHOLD_LOW = 35.0
PING_THRESHOLD_MEDIUM = 60.0


CHARSET = {
    0: 46,
    1: 35,
    2: 35,
    3: 35,
    4: 35,
    5: 46,
    6: 35,
    7: 35,
    8: 35,
    9: 35,
    11: 35,
    12: 32,
    13: 62,
    14: 46,
    15: 46,
    16: 91,
    17: 93,
    18: 48,
    19: 49,
    20: 50,
    21: 51,
    22: 52,
    23: 53,
    24: 54,
    25: 55,
    26: 56,
    27: 57,
    28: 46,
    29: 32,
    30: 32,
    31: 32,
    127: 32,
    128: 40,
    129: 61,
    130: 41,
    131: 35,
    132: 35,
    133: 46,
    134: 35,
    135: 35,
    136: 35,
    137: 35,
    139: 35,
    140: 32,
    141: 62,
    142: 46,
    143: 46,
}


DARK_BG = '#282c34'
DARK_FG = '#abb2bf'
ACCENT_COLOR = '#61afef'
BUTTON_BG = '#3e4451'
BUTTON_FG = DARK_FG
SELECTED_BG = '#4b5263'
ERROR_COLOR = '#e06c75'
SPECTATOR_BG = '#3e4451'
REFRESH_ACTIVE_COLOR = '#d9534f'


ODD_ROW_BG = DARK_BG
EVEN_ROW_BG = '#30343c'


PING_LOW_COLOR = '#5cb85c'
PING_MEDIUM_COLOR = '#f0ad4e'
PING_HIGH_COLOR = '#d9534f'


def quake_chars(data):
    data = bytearray(data)
    for i in range(len(data)):
        if 31 < data[i] < 127:
            continue
        if 143 < data[i] < 255:
            data[i] = data[i] - 128
        if data[i] in CHARSET:
            data[i] = CHARSET[data[i]]
    return data


def udp_command(address, port, data):
    client = None
    try:
        try:
            ip_address = socket.gethostbyname(address)
        except socket.gaierror as e:
            return {"error": f"DNS resolution failed for {address}: {e}"}, None, None
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(UDP_TIMEOUT)
        try:
            client.bind(('', 0))
        except socket.error:
            pass
        buf = b'\xFF\xFF\xFF\xFF' + data.encode('ascii')
        send_time = time.time()
        client.sendto(buf, (ip_address, port))
        msg, server_addr = client.recvfrom(4096)
        ping_time_calc = (time.time() - send_time) * 1000
        return None, msg, ping_time_calc
    except socket.timeout:
        return {"error": "timeout"}, None, None
    except socket.error as e:
        return {"error": str(e)}, None, None
    except Exception as e:
        return {"error": str(e)}, None, None
    finally:
        if client:
             client.close()


def parse_status_response(data):
    try:
        data_after_quake_chars = quake_chars(data).decode('ascii', errors='ignore')
        lines = data_after_quake_chars[6:-2].split('\n')
        server_info = {}
        players = []
        if lines:
            first_line_raw = lines.pop(0)
            tmp_parts = [part for part in first_line_raw.split('\\') if part]
            i = 0
            while i < len(tmp_parts) - 1:
                key_candidate = tmp_parts[i]
                value_candidate = tmp_parts[i+1]
                if key_candidate == 'hostname' and 'hostname' not in server_info:
                    server_info['hostname'] = value_candidate
                    i += 2
                    continue
                elif key_candidate == 'map' and 'map' not in server_info:
                    server_info['map'] = value_candidate
                    i += 2
                    continue
                elif key_candidate == 'mode' and 'mode' not in server_info:
                    server_info['mode'] = value_candidate
                    i += 2
                    continue
                elif value_candidate == 'hostname' and 'hostname' not in server_info:
                    server_info['hostname'] = key_candidate
                    i += 2
                    continue
                elif value_candidate == 'map' and 'map' not in server_info:
                    server_info['map'] = key_candidate
                    i += 2
                    continue
                elif value_candidate == 'mode' and 'mode' not in server_info:
                    server_info['mode'] = value_candidate
                    i += 2
                    continue
                try:
                    server_info[key_candidate] = value_candidate if isNaN(value_candidate) else int(value_candidate)
                except ValueError: 
                    pass
                i += 2
        for p_line in lines:
            if not p_line.strip():
                continue
            match = re.match(r'^(-?\d+)\s+(-?[S\d]+)\s+(-?\d+)\s+(-?\d+)\s*\s*"(.*?)"\s*"(.*?)"\s*(\d+)\s*(\d+)(?:\s"(.*?)"|$)', p_line)
            if match:
                try:
                    player_info = {
                        'id': int(match.group(1)),
                        'frags': match.group(2) if match.group(2) == 'S' else int(match.group(2)),
                        'time': int(match.group(3)),
                        'ping': int(match.group(4)),
                        'name': match.group(5),
                        'skin': match.group(6),
                        'topcolor': int(match.group(7)),
                        'bottomcolor': int(match.group(8)),
                        'team': match.group(9) if match.group(9) is not None else ''
                    }
                    players.append(player_info)
                except (ValueError, TypeError):
                    pass
        server_info['players'] = players
        return server_info
    except Exception as e:
        return {"error": f"parse error: {str(e)}"}


def isNaN(value):
    try:
        int(value)
        return False
    except ValueError:
        return True


def read_servers_from_file_raw(file_path):
    servers = []
    print(f"Attempting to read server list from local file: '{file_path}'")
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    address_or_hostname, port_str = line.split(':')
                    port = int(port_str)
                    if port == 30000 or port == 28000:
                        continue
                    try:
                        servers.append((address_or_hostname, port)) 
                    except ValueError:
                         print(f"Warning: Invalid port for server '{address_or_hostname}:{port_str}'. Skipping.")
    except FileNotFoundError:
        messagebox.showerror("File Error", f"Server list file '{file_path}' not found. Please ensure it exists.")
        return []
    except Exception as e:
        messagebox.showerror("File Error", f"Error reading or parsing server list file '{file_path}': {e}")
        return []
    print(f"Loaded {len(servers)} servers from local file '{file_path}'.")
    return servers


class QuakeWorldGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("QuakeWorld Server Pinger")
        self.root.iconbitmap('uttanka.ico')
        self.servers = []
        self.server_data = {}
        self.favorite_servers_data = {}
        self.all_players_data_flattened = []
        self.gui_lock = Lock()
        self.stop_event = Event()
        self.gui_queue = queue.Queue()

        self.open_detail_windows = {} 

        self._apply_dark_theme()

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        self.root.minsize(900, 600)

        self.notebook = ttk.Notebook(root)
        self.notebook.grid(row=0, column=0, columnspan=2, sticky='nsew', padx=5, pady=5)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # All Servers Tab
        self.all_servers_frame = ttk.Frame(self.notebook, style='TFrame')
        self.notebook.add(self.all_servers_frame, text='All Servers')
        self.all_servers_tree = ttk.Treeview(self.all_servers_frame, columns=('Name', 'Port', 'Ping', 'Map', 'Players'), show='headings', style='Treeview')
        self.all_servers_tree.tag_configure('oddrow', background=ODD_ROW_BG, foreground=DARK_FG)
        self.all_servers_tree.tag_configure('evenrow', background=EVEN_ROW_BG, foreground=DARK_FG)
        self.all_servers_tree.tag_configure('ping_low', background=PING_LOW_COLOR, foreground=DARK_BG)
        self.all_servers_tree.tag_configure('ping_medium', background=PING_MEDIUM_COLOR, foreground=DARK_BG)
        self.all_servers_tree.tag_configure('ping_high', background=PING_HIGH_COLOR, foreground=DARK_BG)
        self.all_servers_tree.tag_configure('ping_error', background=PING_HIGH_COLOR, foreground=DARK_BG)
        self.all_servers_tree.heading('Name', text='Server Name / Address', command=lambda: self.sort_column_by('Name', self.all_servers_tree))
        self.all_servers_tree.heading('Port', text='Port', command=lambda: self.sort_column_by('Port', self.all_servers_tree))
        self.all_servers_tree.heading('Ping', text='Ping (ms)', command=lambda: self.sort_column_by('Ping', self.all_servers_tree))
        self.all_servers_tree.heading('Map', text='Map', command=lambda: self.sort_column_by('Map', self.all_servers_tree))
        self.all_servers_tree.heading('Players', text='Players', command=lambda: self.sort_column_by('Players', self.all_servers_tree))
        self.all_servers_tree.column('Name', width=200, minwidth=150, stretch=True, anchor='w')
        self.all_servers_tree.column('Port', width=60, minwidth=50, stretch=False, anchor='center')
        self.all_servers_tree.column('Ping', width=80, minwidth=60, stretch=False, anchor='center')
        self.all_servers_tree.column('Map', width=120, minwidth=80, stretch=False, anchor='center')
        self.all_servers_tree.column('Players', width=70, minwidth=50, stretch=False, anchor='center')
        all_servers_scrollbar = ttk.Scrollbar(self.all_servers_frame, orient='vertical', command=self.all_servers_tree.yview)
        self.all_servers_tree.configure(yscrollcommand=all_servers_scrollbar.set)
        self.all_servers_tree.grid(row=0, column=0, sticky='nsew')
        all_servers_scrollbar.grid(row=0, column=1, sticky='ns')
        self.all_servers_tree.bind("<Double-1>", self.show_server_details)
        self.all_servers_frame.grid_rowconfigure(0, weight=1)
        self.all_servers_frame.grid_columnconfigure(0, weight=1)

        # Favorites Tab
        self.favorites_frame = ttk.Frame(self.notebook, style='TFrame')
        self.notebook.add(self.favorites_frame, text='Favorites')
        self.favorites_tree = ttk.Treeview(self.favorites_frame, columns=('Name', 'Port', 'Ping', 'Map', 'Players'), show='headings', style='Treeview')
        self.favorites_tree.tag_configure('oddrow', background=ODD_ROW_BG, foreground=DARK_FG)
        self.favorites_tree.tag_configure('evenrow', background=EVEN_ROW_BG, foreground=DARK_FG)
        self.favorites_tree.tag_configure('ping_low', background=PING_LOW_COLOR, foreground=DARK_BG)
        self.favorites_tree.tag_configure('ping_medium', background=PING_MEDIUM_COLOR, foreground=DARK_BG)
        self.favorites_tree.tag_configure('ping_high', background=PING_HIGH_COLOR, foreground=DARK_BG)
        self.favorites_tree.tag_configure('ping_error', background=PING_HIGH_COLOR, foreground=DARK_BG)
        self.favorites_tree.heading('Name', text='Server Name / Address', command=lambda: self.sort_column_by('Name', self.favorites_tree))
        self.favorites_tree.heading('Port', text='Port', command=lambda: self.sort_column_by('Port', self.favorites_tree))
        self.favorites_tree.heading('Ping', text='Ping (ms)', command=lambda: self.sort_column_by('Ping', self.favorites_tree))
        self.favorites_tree.heading('Map', text='Map', command=lambda: self.sort_column_by('Map', self.favorites_tree))
        self.favorites_tree.heading('Players', text='Players', command=lambda: self.sort_column_by('Players', self.favorites_tree))
        self.favorites_tree.column('Name', width=200, minwidth=150, stretch=True, anchor='w')
        self.favorites_tree.column('Port', width=60, minwidth=50, stretch=False, anchor='center')
        self.favorites_tree.column('Ping', width=80, minwidth=60, stretch=False, anchor='center')
        self.favorites_tree.column('Map', width=120, minwidth=80, stretch=False, anchor='center')
        self.favorites_tree.column('Players', width=70, minwidth=50, stretch=False, anchor='center')
        favorites_scrollbar = ttk.Scrollbar(self.favorites_frame, orient='vertical', command=self.favorites_tree.yview)
        self.favorites_tree.configure(yscrollcommand=favorites_scrollbar.set)
        self.favorites_tree.grid(row=0, column=0, sticky='nsew')
        favorites_scrollbar.grid(row=0, column=1, sticky='ns')
        self.favorites_tree.bind("<Double-1>", self.show_server_details)
        self.favorites_frame.grid_rowconfigure(0, weight=1)
        self.favorites_frame.grid_columnconfigure(0, weight=1)

        # Players Tab
        self.players_frame = ttk.Frame(self.notebook, style='TFrame')
        self.notebook.add(self.players_frame, text='Players')
        self.player_search_container = ttk.Frame(self.players_frame, style='TFrame')
        self.player_search_container.grid(row=0, column=0, columnspan=2, sticky='ew', padx=5, pady=5)
        ttk.Label(self.player_search_container, text="Search Player:", style='TLabel').pack(side='left', padx=5)
        self.player_search_var = tk.StringVar(value="")
        self.player_search_entry = ttk.Entry(self.player_search_container, textvariable=self.player_search_var, width=20, style='TEntry')
        self.player_search_entry.pack(side='left', padx=5)
        self.player_search_entry.bind("<KeyRelease>", self._apply_player_search_filter)
        self.players_tree = ttk.Treeview(self.players_frame, columns=('Player Name', 'Server', 'Map', 'Frags', 'Ping', 'Team'), show='headings', style='Treeview')
        self.players_tree.tag_configure('oddrow', background=ODD_ROW_BG, foreground=DARK_FG)
        self.players_tree.tag_configure('evenrow', background=EVEN_ROW_BG, foreground=DARK_FG)
        self.players_tree.heading('Player Name', text='Player Name', command=lambda: self.sort_column_by('Player Name', self.players_tree))
        self.players_tree.heading('Server', text='Server', command=lambda: self.sort_column_by('Server', self.players_tree))
        self.players_tree.heading('Map', text='Map', command=lambda: self.sort_column_by('Map', self.players_tree))
        self.players_tree.heading('Frags', text='Frags', command=lambda: self.sort_column_by('Frags', self.players_tree))
        self.players_tree.heading('Ping', text='Ping', command=lambda: self.sort_column_by('Ping', self.players_tree))
        self.players_tree.heading('Team', text='Team', command=lambda: self.sort_column_by('Team', self.players_tree))
        self.players_tree.column('Player Name', width=150, minwidth=120, stretch=True, anchor='w')
        self.players_tree.column('Server', width=150, minwidth=120, stretch=False, anchor='w')
        self.players_tree.column('Map', width=100, minwidth=80, stretch=False, anchor='center')
        self.players_tree.column('Frags', width=60, minwidth=50, stretch=False, anchor='center')
        self.players_tree.column('Ping', width=60, minwidth=50, stretch=False, anchor='center')
        self.players_tree.column('Team', width=80, minwidth=60, stretch=False, anchor='center')
        players_scrollbar = ttk.Scrollbar(self.players_frame, orient='vertical', command=self.players_tree.yview)
        self.players_tree.configure(yscrollcommand=players_scrollbar.set)
        self.players_tree.grid(row=1, column=0, sticky='nsew')
        players_scrollbar.grid(row=1, column=1, sticky='ns')
        self.players_tree.bind("<Double-1>", self.show_server_details)
        self.players_frame.grid_rowconfigure(1, weight=1)
        self.players_frame.grid_columnconfigure(0, weight=1)

        # Settings Tab (NEW)
        self.settings_frame = ttk.Frame(self.notebook, style='TFrame')
        self.notebook.add(self.settings_frame, text='Settings')
        settings_content_frame = ttk.Frame(self.settings_frame, style='TFrame')
        settings_content_frame.pack(padx=10, pady=10, anchor='nw')
        settings_content_frame.columnconfigure(1, weight=1)

        ttk.Label(settings_content_frame, text="eu-sv.txt URL:", style='TLabel').grid(row=0, column=0, sticky='w', pady=2, padx=2)
        self.eu_sv_url_var = tk.StringVar(value="")
        self.eu_sv_url_entry = ttk.Entry(settings_content_frame, textvariable=self.eu_sv_url_var, width=50, style='TEntry')
        self.eu_sv_url_entry.grid(row=0, column=1, sticky='ew', pady=2, padx=2)
        self.eu_sv_url_entry.bind("<FocusOut>", lambda e: self._save_settings())
        
        ttk.Label(settings_content_frame, text="Max Ping (ms):", style='TLabel').grid(row=1, column=0, sticky='w', pady=2, padx=2)
        self.ping_threshold_var = tk.StringVar()
        self.ping_threshold_entry = ttk.Entry(settings_content_frame, textvariable=self.ping_threshold_var, width=10, style='TEntry')
        self.ping_threshold_entry.grid(row=1, column=1, sticky='w', pady=2, padx=2)
        self.ping_threshold_entry.bind("<KeyRelease>", self._on_ping_threshold_change)
        self.ping_threshold_entry.bind("<FocusOut>", lambda e: self._save_settings())

        self.refresh_eu_sv_button = ttk.Button(settings_content_frame, text="Refresh Server List (eu-sv.txt)", command=self._refresh_server_list_action, style='TButton')
        self.refresh_eu_sv_button.grid(row=2, column=0, columnspan=2, pady=(10,0), sticky='w')


        # Main action buttons container. Aligns to grid(row=1, column=0) of root.
        self.main_buttons_frame = ttk.Frame(root, style='TFrame')
        self.main_buttons_frame.grid(row=1, column=0, columnspan=2, sticky='w', pady=10, padx=5) # Left-aligns entire button frame.
                                                                                           # column 0 is chosen here because no other element uses it on root row 1 anymore.
                                                                                           # columnspan=2 so it effectively spans the width, but sticky='w' makes it cling left.

        self.ping_all_button = ttk.Button(self.main_buttons_frame, text="Ping All Servers", command=self.ping_all, style='TButton')
        self.ping_all_button.pack(side='left', padx=5)
        
        self.copy_address_button = ttk.Button(self.main_buttons_frame, text="Copy Address", command=self._copy_selected_address_to_clipboard, style='TButton')
        self.copy_address_button.pack(side='left', padx=5)
        
        ttk.Button(self.main_buttons_frame, text="Add to Favorites", command=self._add_to_favorites_action, style='TButton').pack(side='left', padx=5)
        
        self.remove_from_favorites_button = ttk.Button(self.main_buttons_frame, text="Remove from Favorites", command=self._remove_from_favorites_action, style='TButton')
        self.remove_from_favorites_button.pack(side='left', padx=5)

        self.save_all_servers_button = ttk.Button(self.main_buttons_frame, text="Save All Servers", command=self._save_servers_to_cache, style='TButton')
        self.save_all_servers_button.pack(side='left', padx=5)
        
        self.root.after(0, self._on_tab_select, None)

        self.all_servers_items = {}
        self.favorites_items = {}

        self.progressbar = ttk.Progressbar(root, orient='horizontal', mode='determinate')
        self.root.grid_rowconfigure(2, weight=0)

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_select)

        self._load_settings()
        self._load_server_cache()

        self._load_favorites()
        self._populate_initial_treeview_main_and_favorites()

        self.root.after(100, self.process_gui_queue)


    def _apply_dark_theme(self):
        s = ttk.Style()
        s.theme_use('clam')
        self.root.config(bg=DARK_BG)
        s.configure('.', background=DARK_BG, foreground=DARK_FG, bordercolor=DARK_BG)
        s.configure('TFrame', background=DARK_BG, foreground=DARK_FG, bordercolor=DARK_BG)
        s.configure('TLabel', background=DARK_BG, foreground=DARK_FG)
        # Apply default button style (will be overridden for active refresh)
        s.configure('TButton', background=BUTTON_BG, foreground=BUTTON_FG, borderwidth=1, focusthickness=3, focuscolor=ACCENT_COLOR)
        s.map('TButton', background=[('active', ACCENT_COLOR)])
        # New styles for refresh buttons
        s.configure('RefreshNormal.TButton', background=BUTTON_BG, foreground=BUTTON_FG, borderwidth=1)
        s.map('RefreshNormal.TButton', background=[('active', ACCENT_COLOR)])
        s.configure('RefreshActive.TButton', background=REFRESH_ACTIVE_COLOR, foreground=BUTTON_FG, borderwidth=1) # Red background
        s.map('RefreshActive.TButton', background=[('active', REFRESH_ACTIVE_COLOR)]) # Stay red when active state is clicked

        s.configure('TEntry', fieldbackground=BUTTON_BG, foreground=DARK_FG, insertcolor=DARK_FG, bordercolor=ACCENT_COLOR)
        s.configure('Treeview',
                    background=DARK_BG,
                    foreground=DARK_FG,
                    fieldbackground=DARK_BG,
                    borderwidth=0,
                    highlightthickness=0,
                    relief='flat')
        s.map('Treeview', background=[('selected', SELECTED_BG)], foreground=[('selected', DARK_FG)])
        s.configure('Treeview.Heading',
                    background=BUTTON_BG,
                    foreground=DARK_FG,
                    font=('TkDefaultFont', 10, 'bold'),
                    borderwidth=0,
                    highlightthickness=0,
                    relief='flat')
        s.map('Treeview.Heading', background=[('active', ACCENT_COLOR)])
        s.configure("Vertical.TScrollbar", background=BUTTON_BG, troughcolor=DARK_BG, bordercolor=DARK_BG, arrowcolor=DARK_FG)
        s.map("Vertical.TScrollbar", background=[('active', ACCENT_COLOR)], arrowcolor=[('active', DARK_FG)])
        s.configure('TNotebook', background=DARK_BG, borderwidth=0)
        s.configure('TNotebook.Tab', background=BUTTON_BG, foreground=DARK_FG, borderwidth=0)
        s.map('TNotebook.Tab', background=[('selected', ACCENT_COLOR)], foreground=[('selected', DARK_BG)])
        s.configure("TProgressbar", foreground=ACCENT_COLOR, background=BUTTON_BG, troughcolor=DARK_BG, bordercolor=DARK_BG)
        self.root.option_add("*background", DARK_BG)
        self.root.option_add("*foreground", DARK_FG)
        self.root.option_add("*Toplevel.background", DARK_BG)


    def process_gui_queue(self):
        try:
            while True:
                func, args, kwargs = self.gui_queue.get(block=False)
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error executing GUI task in main thread: {e}. Task: {func.__name__} args={args} kwargs={kwargs}", exc_info=True)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_gui_queue)

    def _load_settings(self):
        print(f"Attempting to load settings from {SETTINGS_FILE}...")
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                ping_threshold = settings.get('max_ping_threshold', '')
                self.ping_threshold_var.set(ping_threshold)
                eu_sv_url = settings.get('eu_sv_url', '')
                self.eu_sv_url_var.set(eu_sv_url)
                print(f"Loaded settings: max_ping_threshold='{ping_threshold}', eu_sv_url='{eu_sv_url}'.")
        except FileNotFoundError:
            print(f"'{SETTINGS_FILE}' not found. Using default settings.")
            self.ping_threshold_var.set("")
            self.eu_sv_url_var.set("")
        except json.JSONDecodeError as e:
            print(f"Error reading settings file: {e}. Using default settings.")
            self.ping_threshold_var.set("")
            self.eu_sv_url_var.set("")

    def _save_settings(self):
        print(f"Saving settings to {SETTINGS_FILE}...")
        settings = {
            'max_ping_threshold': self.ping_threshold_var.get(),
            'eu_sv_url': self.eu_sv_url_var.get()
        }
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
            print("Settings saved successfully.")
        except IOError as e:
            print(f"Error saving settings to {SETTINGS_FILE}: {e}")

    def _load_server_cache(self):
        print(f"Attempting to load server cache from {SERVERS_CACHE_FILE}...")
        loaded_servers_from_cache = {}
        cache_loaded_successfully = False
        try:
            with open(SERVERS_CACHE_FILE, 'r') as f:
                cached_list = json.load(f)
                for server_info in cached_list:
                    ip = server_info['original_ip']
                    port = server_info['port']
                    server_key = (ip, port)
                    loaded_servers_from_cache[server_key] = server_info
                print(f"Loaded {len(loaded_servers_from_cache)} servers from cache file '{SERVERS_CACHE_FILE}'.")
                cache_loaded_successfully = True
        except FileNotFoundError:
            print(f"'{SERVERS_CACHE_FILE}' not found. Will try to fetch from eu-sv.txt source.")
        except json.JSONDecodeError as e:
            print(f"Error reading server cache file: {e}. Will try to fetch from eu-sv.txt source.")

        with self.gui_lock:
            self.server_data = loaded_servers_from_cache
            if not cache_loaded_successfully:
                self._fetch_servers_from_source_and_update_main_list_sync()

            self.servers = []
            for server_key in self.server_data:
                data = self.server_data[server_key]
                self.servers.append((data['display_hostname'], data['port'], data['original_ip']))

        print(f"Combined server list now contains {len(self.servers)} entries.")


    def _save_servers_to_cache(self):
        print(f"Saving all server data to {SERVERS_CACHE_FILE}...")
        serializable_servers = []
        with self.gui_lock:
            for server_info in self.server_data.values():
                serializable_servers.append(server_info) 
        
        try:
            with open(SERVERS_CACHE_FILE, 'w') as f:
                json.dump(serializable_servers, f, indent=2)
            self.gui_queue.put((messagebox.showinfo, ("Save Servers", "All server data saved successfully!"), {}))
            print("All server data saved successfully.")
        except IOError as e:
            self.gui_queue.put((messagebox.showerror, ("Save Servers Error", f"Error saving server data: {e}"), {}))
            print(f"Error saving all server data to {SERVERS_CACHE_FILE}: {e}")

    def _refresh_server_list_action(self):
        print("User initiated server list refresh from eu-sv.txt source.")
        self.gui_queue.put((self.refresh_eu_sv_button.config, (), {'state': 'disabled', 'style': 'RefreshActive.TButton'}))
        
        Thread(target=self._fetch_servers_from_source_and_update_main_list_async, name="RefreshEUSVThread").start()

    def _fetch_servers_from_source_and_update_main_list_async(self):
        self._fetch_servers_from_source_and_update_main_list_sync()
        self.gui_queue.put((self.refresh_eu_sv_button.config, (), {'state': 'normal', 'style': 'RefreshNormal.TButton'}))
        self.gui_queue.put((self._populate_initial_treeview_main_and_favorites, (), {}))
        self.gui_queue.put((self._load_favorites, (), {}))
        self.gui_queue.put((self._aggregate_and_populate_player_data, (), {}))


    def _fetch_servers_from_source_and_update_main_list_sync(self):
        configured_url = self.eu_sv_url_var.get().strip()
        server_lines = []
        source_description = ""

        if configured_url:
            source_description = f"URL: {configured_url}"
            print(f"Attempting to download eu-sv.txt from {configured_url}...")
            try:
                response = requests.get(configured_url, timeout=10)
                response.raise_for_status()
                server_lines = response.text.splitlines()
                print(f"Successfully downloaded {len(server_lines)} lines from URL.")
            except requests.exceptions.RequestException as e:
                self.gui_queue.put((messagebox.showerror, ("Download Error", f"Failed to download eu-sv.txt from URL '{configured_url}': {e}"), {}))
                print(f"Error downloading from URL: {e}. Falling back to local file.")
                server_lines = self._read_local_eu_sv_content()
                source_description = f"local file: {LOCAL_SERVER_LIST_FILE} (fallback)"
        else:
            source_description = f"local file: {LOCAL_SERVER_LIST_FILE}"
            server_lines = self._read_local_eu_sv_content()
        
        if not server_lines:
             self.gui_queue.put((messagebox.showinfo, ("Server List Empty", f"Could not load any servers from {source_description}."), {}))
             return

        new_servers_list = []
        newly_added_count = 0
        updated_count = 0
        with self.gui_lock:
            fetched_server_keys = set()
            for line in server_lines:
                line = line.strip()
                if line and ':' in line:
                    address_or_hostname, port_str = line.split(':')
                    try:
                        port = int(port_str)
                        if port == 30000 or port == 28000: continue
                        ip_for_key = ""
                        try:
                            ip_for_key = socket.gethostbyname(address_or_hostname)
                        except socket.gaierror:
                            ip_for_key = address_or_hostname
                        fetched_server_keys.add((ip_for_key, port))
                    except (ValueError, socket.gaierror):
                        pass

            servers_to_remove = []
            for server_key in self.server_data.keys():
                if server_key not in fetched_server_keys:
                    servers_to_remove.append(server_key)
            
            for key in servers_to_remove:
                del self.server_data[key]
            print(f"Removed {len(servers_to_remove)} servers from cache no longer present in source.")

            for line in server_lines:
                line = line.strip()
                if line and ':' in line:
                    address_or_hostname, port_str = line.split(':')
                    try:
                        port = int(port_str)
                        if port == 30000 or port == 28000:
                            continue

                        actual_ip = ""
                        try:
                            actual_ip = socket.gethostbyname(address_or_hostname)
                        except socket.gaierror:
                            actual_ip = address_or_hostname
                            
                        server_key = (actual_ip, port)
                        existing_data = self.server_data.get(server_key, None)

                        if existing_data is None:
                            self.server_data[server_key] = {
                                'original_ip': actual_ip,
                                'display_hostname': address_or_hostname,
                                'port': port,
                                'ping': 'N/A', 'map': 'N/A', 'players_count': 'N/A',
                                'spectators_count': 'N/A', 'players': [], 'mode': 'N/A'
                            }
                            newly_added_count += 1
                        else:
                             if existing_data['display_hostname'] == existing_data['original_ip'] or existing_data['display_hostname'] != address_or_hostname:
                                 existing_data['display_hostname'] = address_or_hostname
                                 updated_count += 1
                        
                        new_servers_list.append((self.server_data[server_key]['display_hostname'], port, actual_ip))

                    except ValueError:
                        print(f"Warning: Invalid port for server '{address_or_hostname}:{port_str}'. Skipping.")
            
            self.servers = new_servers_list

        print(f"Finished fetching server list from {source_description}. Added {newly_added_count} new servers, updated {updated_count} existing. Total servers in main list: {len(self.servers)}")
        self.gui_queue.put((messagebox.showinfo, ("Server List Updated", f"Refreshed server list from {source_description}. Added {newly_added_count} new servers and updated {updated_count} existing entries. {len(servers_to_remove)} old servers removed."), {}))

    def _read_local_eu_sv_content(self):
        """Helper to read eu-sv.txt from local file and return lines."""
        try:
            with open(LOCAL_SERVER_LIST_FILE, 'r') as f:
                return f.readlines()
        except FileNotFoundError:
            self.gui_queue.put((messagebox.showerror, ("File Error", f"Local server list file '{LOCAL_SERVER_LIST_FILE}' not found."), {}))
            return []
        except Exception as e:
            self.gui_queue.put((messagebox.showerror, ("File Read Error", f"Error reading local server list file: {e}"), {}))
            return []


    def _load_favorites(self):
        print(f"Attempting to load favorites from {FAVORITES_FILE}...")
        try:
            with open(FAVORITES_FILE, 'r') as f:
                loaded_favorites_list = json.load(f)
                self.favorite_servers_data = {}
                for fav_server_info in loaded_favorites_list:
                    ip = fav_server_info['original_ip']
                    port = fav_server_info['port']
                    server_key = (ip, port)
                    if server_key in self.server_data:
                        self.favorite_servers_data[server_key] = self.server_data[server_key].copy()
                    else:
                        self.favorite_servers_data[server_key] = fav_server_info
                print(f"Loaded {len(self.favorite_servers_data)} favorite servers.")
        except FileNotFoundError:
            print(f"'{FAVORITES_FILE}' not found. Starting with empty favorites.")
            self.favorite_servers_data = {}
        except json.JSONDecodeError as e:
            print(f"Error reading favorites file: {e}. Starting with empty favorites.")
            self.favorite_servers_data = {}

    def _save_favorites(self):
        print(f"Saving {len(self.favorite_servers_data)} favorite servers to {FAVORITES_FILE}...")
        serializable_favorites = []
        for server_info in self.favorite_servers_data.values():
            serializable_favorites.append(server_info) 
        try:
            with open(FAVORITES_FILE, 'w') as f:
                json.dump(serializable_favorites, f, indent=2)
            print("Favorites saved successfully.")
        except IOError as e:
            print(f"Error saving favorites to {FAVORITES_FILE}: {e}")


    def _on_closing(self):
        print("Closing application. Signaling threads to stop.")
        self.stop_event.set()
        self._save_settings()
        self._save_servers_to_cache()
        self._save_favorites()

        for server_key in list(self.open_detail_windows.keys()):
            self._on_detail_window_closing_handler(server_key)
        self.root.destroy()


    def _populate_initial_treeview_main_and_favorites(self):
        print("Populating initial treeviews for 'All Servers' and 'Favorites'.")
        self.all_servers_tree.delete(*self.all_servers_tree.get_children())
        self.all_servers_items = {}
        self.favorites_tree.delete(*self.favorites_tree.get_children())
        self.favorites_items = {}

        for index, (initial_display_name, port, actual_ip) in enumerate(self.servers):
            server_key = (actual_ip, port)
            data = self.server_data.get(server_key, {
                'original_ip': actual_ip, 'display_hostname': initial_display_name,
                'port': port, 'ping': 'N/A', 'map': 'N/A', 'players_count': 'N/A',
                'spectators_count': 'N/A', 'players': [], 'mode': 'N/A'
            })
            values = (data['display_hostname'], data['port'], data['ping'], data['map'], data['players_count'])
            
            tag = 'evenrow' if index % 2 == 0 else 'oddrow'
            item_id = self.all_servers_tree.insert('', 'end', values=values, tags=(tag,))
            self.all_servers_items[server_key] = item_id
        print(f"Inserted {len(self.all_servers_items)} items into 'All Servers' tree.")

        for index, (server_key, data) in enumerate(self.favorite_servers_data.items()):
            actual_data = self.server_data.get(server_key, data)
            values = (actual_data['display_hostname'], actual_data['port'], actual_data['ping'], actual_data['map'], actual_data['players_count'])
            
            tag = 'evenrow' if index % 2 == 0 else 'oddrow'
            item_id = self.favorites_tree.insert('', 'end', values=values, tags=(tag,))
            self.favorites_items[server_key] = item_id
        print(f"Inserted {len(self.favorites_items)} items into 'Favorites' tree.")


    def sort_column_by(self, col, treeview):
        with self.gui_lock:
            if not hasattr(treeview, '_sort_column'):
                treeview._sort_column = None
                treeview._sort_reverse = False

            items = [(treeview.item(item)['values'], item) for item in treeview.get_children()]
            
            if treeview == self.players_tree:
                col_map = {'Player Name': 0, 'Server': 1, 'Map': 2, 'Frags': 3, 'Ping': 4, 'Team': 5}
            else:
                col_map = {'Name': 0, 'Port': 1, 'Ping': 2, 'Map': 3, 'Players': 4}
            col_index = col_map[col]

            def sort_key(item):
                value = item[0][col_index]
                if col in ('Port', 'Players'):
                    try:
                        return int(value)
                    except ValueError:
                        return float('inf')
                elif col in ('Ping', 'Frags'):
                    try:
                        return float(str(value).split()[0])
                    except (ValueError, IndexError):
                        return float('inf')
                return str(value).lower()

            items.sort(key=sort_key, reverse=treeview._sort_reverse)
            for index, (_, item_id) in enumerate(items):
                treeview.detach(item_id)
                
                existing_tags = set(treeview.item(item_id, 'tags'))
                new_zebra_tag = 'evenrow' if index % 2 == 0 else 'oddrow'
                
                ping_color_tag = ''
                if treeview != self.players_tree:
                    ping_str_from_values = treeview.item(item_id, 'values')[2]
                    ping_color_tag = self._get_ping_color_tag(ping_str_from_values)

                tags_to_apply = (existing_tags - {'oddrow', 'evenrow', 'ping_low', 'ping_medium', 'ping_high', 'ping_error', 'spectator_row'}) | {new_zebra_tag}
                if ping_color_tag:
                    tags_to_apply.add(ping_color_tag)
                
                treeview.item(item_id, tags=tuple(tags_to_apply))
                treeview.move(item_id, '', 'end')

            if treeview._sort_column == col:
                treeview._sort_reverse = not treeview._sort_reverse
            else:
                treeview._sort_column = col
                treeview._sort_reverse = False


    def _get_ping_color_tag(self, ping_value_str):
        if ping_value_str.startswith('Error') or ping_value_str == 'N/A':
            return 'ping_error'
        try:
            ping_value = float(ping_value_str)
            if ping_value <= PING_THRESHOLD_LOW:
                return 'ping_low'
            elif ping_value <= PING_THRESHOLD_MEDIUM:
                return 'ping_medium'
            else:
                return 'ping_high'
        except ValueError:
            return 'ping_error'


    def ping_server(self, initial_display_name, port, actual_ip):
        if self.stop_event.is_set():
            return
        server_key = (actual_ip, port)
        err, response, ping_time = udp_command(actual_ip, port, 'status 31\0')
        current_server_data = {}

        if err:
            values_for_treeview = (initial_display_name, port, f"Error: {err['error']}", 'N/A', 'N/A')
            current_server_data = {
                'original_ip': actual_ip,
                'display_hostname': initial_display_name,
                'port': port,
                'ping': f"Error: {err['error']}",
                'map': 'N/A',
                'players_count': 'N/A',
                'spectators_count': 'N/A',
                'players': [],
                'mode': 'N/A'
            }
        else:
            server_info = parse_status_response(response)
            if 'error' in server_info:
                values_for_treeview = (initial_display_name, port, f"Error: {server_info['error']}", 'N/A', 'N/A')
                current_server_data = {
                    'original_ip': actual_ip,
                    'display_hostname': initial_display_name,
                    'port': port,
                    'ping': f"Error: {server_info['error']}",
                    'map': 'N/A',
                    'players_count': 'N/A',
                    'spectators_count': 'N/A',
                    'players': [],
                    'mode': 'N/A'
                }
            else:
                hostname_from_server = server_info.get('hostname')
                map_name = server_info.get('map', 'N/A')
                gamemode_from_server = server_info.get('mode', 'N/A')
                resolved_display_name = hostname_from_server if hostname_from_server and hostname_from_server.strip() else initial_display_name
                all_players = server_info.get('players', [])
                spectators = [p for p in all_players if p.get('frags') == 'S']
                players_count = len(all_players) - len(spectators)
                values_for_treeview = (resolved_display_name, port, f"{ping_time:.2f}", map_name, players_count)
                current_server_data = {
                    'original_ip': actual_ip,
                    'display_hostname': resolved_display_name,
                    'port': port,
                    'ping': f"{ping_time:.2f}",
                    'map': map_name,
                    'players_count': players_count,
                    'spectators_count': len(spectators),
                    'players': all_players,
                    'mode': gamemode_from_server
                }
        with self.gui_lock:
            self.server_data[server_key] = current_server_data.copy()
            if server_key in self.favorite_servers_data:
                 self.favorite_servers_data[server_key].update(current_server_data)
            if server_key in self.open_detail_windows:
                 self.gui_queue.put((self._update_detail_view, (server_key, current_server_data), {}))
        self.gui_queue.put((self.update_server_display, (server_key, values_for_treeview), {}))


    def ping_all(self):
        current_tab_id = self.notebook.select()
        selected_tab_text = self.notebook.tab(current_tab_id, "text")

        servers_to_ping_list = []
        if selected_tab_text == "All Servers":
            print("Initiating 'Ping All Servers' for ALL servers.")
            for name, port, ip in self.servers:
                servers_to_ping_list.append((name, port, ip))
        elif selected_tab_text == "Favorites":
            print("Initiating 'Ping All Servers' for FAVORITE servers only.")
            for fav_key, fav_data in self.favorite_servers_data.items():
                servers_to_ping_list.append((fav_data['display_hostname'], fav_data['port'], fav_data['original_ip']))
        elif selected_tab_text == "Players":
            print("Initiating 'Ping All Servers' for ALL known servers (from players tab).")
            for name, port, ip in self.servers:
                servers_to_ping_list.append((name, port, ip))
        else:
            self.gui_queue.put((messagebox.showwarning, ("Ping Servers", "No active server list selected for pinging."), {}))
            return
            
        all_unique_servers_to_ping = list(set(servers_to_ping_list))

        self.gui_queue.put((self.ping_all_button.config, (), {'state': 'disabled', 'style': 'RefreshActive.TButton'}))
        self.gui_queue.put((self.progressbar.stop, (), {}))
        self.gui_queue.put((self.progressbar.config, (), {'maximum': len(all_unique_servers_to_ping)}))
        self.gui_queue.put((self.progressbar.config, (), {'value': 0}))
        self.gui_queue.put((self.progressbar.grid, (), {'row': 2, 'column': 0, 'columnspan': 2, 'sticky': 'ew', 'padx': 5, 'pady': 2}))

        print(f"Queuing {len(all_unique_servers_to_ping)} unique servers for pinging.")

        def thread_func():
            current_ping_count = 0
            for initial_display_name, port, actual_ip in all_unique_servers_to_ping:
                if self.stop_event.is_set():
                    break
                self.ping_server(initial_display_name, port, actual_ip) 
                current_ping_count += 1
                self.gui_queue.put((self.progressbar.config, (), {'value': current_ping_count}))

            print(f"Ping operation finished.")
            self.gui_queue.put((self.sort_by_ping_and_players, (), {}))
            self.gui_queue.put((self._aggregate_and_populate_player_data, (), {}))
            self.gui_queue.put((self.progressbar.grid_forget, (), {}))
            self.gui_queue.put((self.ping_all_button.config, (), {'state': 'normal', 'style': 'RefreshNormal.TButton'}))


        with self.gui_lock:
            for key in self.server_data:
                self.server_data[key].update({
                    'ping': 'N/A', 'map': 'N/A', 'players_count': 'N/A',
                    'spectators_count': 'N/A',
                    'players': [], 'mode': 'N/A'
                })

            self.all_servers_tree.delete(*self.all_servers_tree.get_children())
            self.all_servers_items = {}
            self.favorites_tree.delete(*self.favorites_tree.get_children())
            self.favorites_items = {}
            self.players_tree.delete(*self.players_tree.get_children())
            self._populate_initial_treeview_main_and_favorites() 
        Thread(target=thread_func, name="PingAllThread").start()


    def sort_by_ping_and_players(self):
        print("Applying ping filter and sorting both server lists.")
        with self.gui_lock:
            ping_threshold_str = self.ping_threshold_var.get().strip()
            ping_threshold = float('inf')
            if ping_threshold_str:
                try:
                    ping_threshold = float(ping_threshold_str)
                except ValueError:
                    self.gui_queue.put((messagebox.showwarning, ("Invalid Input", "Please enter a valid number for Max Ping."), {}))
                    self.gui_queue.put((self.ping_threshold_var.set, ("",), {}))
                    self.gui_queue.put((self._repopulate_all_trees, (False, float('inf')), {}))
                    return
            self.gui_queue.put((self._repopulate_all_trees, (True, ping_threshold), {}))


    def _repopulate_all_trees(self, filter_by_ping=False, ping_threshold=float('inf')):
        self.all_servers_tree.delete(*self.all_servers_tree.get_children())
        self.all_servers_items = {}

        displayable_all_servers = []
        for initial_display_name, port, actual_ip in self.servers:
            server_key = (actual_ip, port)
            data = self.server_data.get(server_key, {'original_ip': actual_ip, 'port': port, 'display_hostname': initial_display_name, 'ping': 'N/A', 'players_count': 'N/A'})

            try:
                ping_val_str = data.get('ping', 'N/A')
                ping_value = float('inf')
                if not ("Error" in ping_val_str or ping_val_str == 'N/A'):
                    ping_value = float(ping_val_str)
                players_count_val = data.get('players_count', 'N/A')
                players_count = -1
                if players_count_val != 'N/A':
                    players_count = int(players_count_val)
                if not filter_by_ping or ping_value <= ping_threshold:
                    displayable_all_servers.append((ping_value, players_count, actual_ip, port, data))
            except (ValueError, TypeError, IndexError):
                if not filter_by_ping:
                    displayable_all_servers.append((float('inf'), -1, actual_ip, port, data))
        
        displayable_all_servers.sort(key=lambda x: (x[0], -x[1]))
        for index, (ping_value, players_count, ip, port, data) in enumerate(displayable_all_servers):
            values = (data['display_hostname'], data['port'], data['ping'], data['map'], data['players_count'])
            zebra_tag = 'evenrow' if index % 2 == 0 else 'oddrow'
            ping_color_tag = self._get_ping_color_tag(data['ping'])
            tags = (zebra_tag, ping_color_tag)
            item_id = self.all_servers_tree.insert('', 'end', values=values, tags=tags)
            self.all_servers_items[(ip, port)] = item_id
        print(f"Refreshed 'All Servers' tree with {len(self.all_servers_items)} items.")

        self.favorites_tree.delete(*self.favorites_tree.get_children())
        self.favorites_items = {}

        displayable_favorites = []
        for (ip, port), data in self.favorite_servers_data.items():
            try:
                current_server_info = self.server_data.get((ip,port), data)
                ping_val_str = current_server_info.get('ping', 'N/A')
                ping_value = float('inf')
                if not ("Error" in ping_val_str or ping_val_str == 'N/A'):
                    ping_value = float(ping_val_str)
                players_count_val = current_server_info.get('players_count', 'N/A')
                players_count = -1
                if players_count_val != 'N/A':
                    players_count = int(players_count_val)
                if not filter_by_ping or ping_value <= ping_threshold:
                    displayable_favorites.append((ping_value, players_count, ip, port, current_server_info))
            except (ValueError, TypeError, IndexError):
                if not filter_by_ping:
                    displayable_favorites.append((float('inf'), -1, ip, port, data))
        
        displayable_favorites.sort(key=lambda x: (x[0], -x[1]))
        for index, (ping_value, players_count, ip, port, data) in enumerate(displayable_favorites):
            values = (data['display_hostname'], data['port'], data['ping'], data['map'], data['players_count'])
            zebra_tag = 'evenrow' if index % 2 == 0 else 'oddrow'
            ping_color_tag = self._get_ping_color_tag(data['ping'])
            tags = (zebra_tag, ping_color_tag)
            item_id = self.favorites_tree.insert('', 'end', values=values, tags=tags)
            self.favorites_items[(ip, port)] = item_id
        print(f"Refreshed 'Favorites' tree with {len(self.favorites_items)} items.")


    def _on_ping_threshold_change(self, event=None):
        self.root.after(100, self.sort_by_ping_and_players)


    def _apply_player_search_filter(self, event=None):
        search_term = self.player_search_var.get().strip()
        self.gui_queue.put((self._populate_player_treeview, (search_term,), {}))


    def _aggregate_and_populate_player_data(self):
        print("Aggregating player data and populating players tree.")
        self.all_players_data_flattened = []
        with self.gui_lock:
            for server_key, server_info in self.server_data.items():
                if not server_info.get('ping', 'N/A').startswith('Error') and server_info.get('ping') != 'N/A':
                    server_display_name = server_info.get('display_hostname', server_key[0])
                    server_map = server_info.get('map', 'N/A')
                    for player in server_info.get('players', []):
                        if player.get('frags') != 'S':
                            self.all_players_data_flattened.append({
                                'player_name': player.get('name', 'N/A'),
                                'server_name': server_display_name,
                                'map': server_map,
                                'frags': player.get('frags', 'N/A'),
                                'ping': player.get('ping', 'N/A'),
                                'team': player.get('team', '')
                            })
        search_term = self.player_search_var.get().strip()
        self.gui_queue.put((self._populate_player_treeview, (search_term,), {}))
        print(f"Aggregated {len(self.all_players_data_flattened)} player entries.")


    def _populate_player_treeview(self, search_term=''):
        print(f"Populating players treeview with search term: '{search_term}'")
        self.players_tree.delete(*self.players_tree.get_children())
        filtered_players = []

        for p_data in self.all_players_data_flattened:
            player_name_lower = p_data.get('player_name', '').lower()
            if not search_term or search_term.lower() in player_name_lower:
                filtered_players.append(p_data)
        
        filtered_players.sort(key=lambda x: (str(x.get('server_name', '')).lower(), str(x.get('player_name', '')).lower()))

        for index, p_data in enumerate(filtered_players):
            zebra_tag = 'evenrow' if index % 2 == 0 else 'oddrow'
            self.players_tree.insert('', 'end',
                                     values=(p_data['player_name'],
                                             p_data['server_name'],
                                             p_data['map'],
                                             p_data['frags'],
                                             p_data['ping'],
                                             p_data['team']),
                                     tags=(zebra_tag,))
        print(f"Inserted {len(filtered_players)} items into 'Players' tree after filtering.")


    def _add_to_favorites_action(self):
        selected_items = self.all_servers_tree.selection()
        if not selected_items:
            self.gui_queue.put((messagebox.showinfo, ("Add to Favorites", "Please select one or more servers to add to favorites."), {}))
            return
        added_count = 0
        duplicate_count = 0
        not_found_count = 0
        for item_id in selected_items:
            found_key = None
            for key, tree_item_id in self.all_servers_items.items():
                if tree_item_id == item_id:
                    found_key = key
                    break
            if found_key:
                if found_key not in self.favorite_servers_data:
                    server_info_to_add = self.server_data.get(found_key)
                    if server_info_to_add:
                        self.favorite_servers_data[found_key] = server_info_to_add.copy()
                        added_count += 1
                    else:
                        not_found_count += 1
                else:
                    duplicate_count += 1
            else:
                not_found_count += 1
        self._update_favorites_tree_display()
        self._save_favorites()
        feedback_message = []
        if added_count > 0:
            feedback_message.append(f"{added_count} server(s) added.")
        if duplicate_count > 0:
            feedback_message.append(f"{duplicate_count} server(s) already in favorites.")
        if not_found_count > 0:
            feedback_message.append(f"{not_found_count} server(s) could not be identified.")
        self.gui_queue.put((messagebox.showinfo, ("Add to Favorites Result", "\n".join(feedback_message) if feedback_message else "No servers were added."), {}))


    def _remove_from_favorites_action(self):
        selected_items = self.favorites_tree.selection()
        if not selected_items:
            self.gui_queue.put((messagebox.showinfo, ("Remove from Favorites", "Please select one or more servers to remove from favorites."), {}))
            return
        removed_count = 0
        not_in_favorites_count = 0
        not_found_count = 0
        for item_id in selected_items:
            found_key = None
            for key, tree_item_id in self.favorites_items.items():
                if tree_item_id == item_id:
                    found_key = key
                    break
            if found_key:
                if found_key in self.favorite_servers_data:
                    del self.favorite_servers_data[found_key]
                    removed_count += 1
                else:
                    not_in_favorites_count += 1
            else:
                not_found_count += 1
        self._update_favorites_tree_display()
        self._save_favorites()
        feedback_message = []
        if removed_count > 0:
            feedback_message.append(f"{removed_count} server(s) removed.")
        if not_in_favorites_count > 0:
            feedback_message.append(f"{not_in_favorites_count} server(s) were not in favorites.")
        if not_found_count > 0:
            feedback_message.append(f"{not_found_count} server(s) could not be identified.")
        self.gui_queue.put((messagebox.showinfo, ("Remove from Favorites Result", "\n".join(feedback_message) if feedback_message else "No servers were removed."), {}))


    def _update_favorites_tree_display(self):
        self.favorites_tree.delete(*self.favorites_tree.get_children())
        self.favorites_items = {}
        displayable_favorites = list(self.favorite_servers_data.values())
        displayable_favorites.sort(key=lambda x: str(x.get('display_hostname', '')).lower())
        for index, data in enumerate(displayable_favorites):
            server_key = (data['original_ip'], data['port'])
            values = (data['display_hostname'], data['port'], data['ping'], data['map'], data['players_count'])
            tag = 'evenrow' if index % 2 == 0 else 'oddrow'
            item_id = self.favorites_tree.insert('', 'end', values=values, tags=(tag,))
            self.favorites_items[server_key] = item_id


    def _copy_selected_address_to_clipboard(self):
        current_tab_id = self.notebook.select()
        if current_tab_id == self.all_servers_frame._w:
            tree_to_use = self.all_servers_tree
            items_map = self.all_servers_items
        elif current_tab_id == self.favorites_frame._w:
            tree_to_use = self.favorites_tree
            items_map = self.favorites_items
        else:
            self.gui_queue.put((messagebox.showerror, ("Error", "No active server list found to copy from."), {}))
            return
        selected_item = tree_to_use.focus()
        if not selected_item:
            self.gui_queue.put((messagebox.showinfo, ("Copy Address", "Please select a server to copy its address."), {}))
            return
        found_key = None
        for key, item_id in items_map.items():
            if item_id == selected_item:
                found_key = key
                break
        if found_key:
            address_to_copy = f"{found_key[0]}:{found_key[1]}"
            self.root.clipboard_clear()
            self.root.clipboard_append(address_to_copy)
            self.gui_queue.put((messagebox.showinfo, ("Copy Address", f"'{address_to_copy}' copied to clipboard."), {}))
        else:
            self.gui_queue.put((messagebox.showerror, ("Error", "Could not identify the selected server to copy address."), {}))


    def connect_to_server(self, address, port):
        client_exec = "ezquake-gl.exe"
        command = [client_exec, f"+connect {address}:{port}"]
        try:
            subprocess.Popen(command, shell=True)
            self.gui_queue.put((messagebox.showinfo, ("Launch Client", f"Attempting to connect to {address}:{port} with '{client_exec}'..."), {}))
        except FileNotFoundError:
            self.gui_queue.put((messagebox.showerror, ("Error", f"QuakeWorld client executable not found. Please ensure '{client_exec}' is in your system's PATH or the application directory."), {}))
        except Exception as e:
            self.gui_queue.put((messagebox.showerror, ("Error", f"Failed to launch QuakeWorld client: {e}"), {}))

    def _on_detail_window_closing_handler(self, server_key):
        if server_key in self.open_detail_windows:
            detail_info = self.open_detail_windows[server_key]
            if detail_info['window'].winfo_exists():
                if detail_info['refresh_job_id'] is not None:
                    detail_info['window'].after_cancel(detail_info['refresh_job_id'])
                detail_info['window'].destroy()
            del self.open_detail_windows[server_key]


    def _update_detail_view(self, server_key, server_detail_data):
        if self.stop_event.is_set() or server_key not in self.open_detail_windows or not self.open_detail_windows[server_key]['window'].winfo_exists():
            return
        detail_window_ref = self.open_detail_windows[server_key]['window']
        detail_labels_ref = detail_window_ref._detail_labels
        detail_player_tree_ref = detail_window_ref._detail_player_tree
        
        detail_window_ref.title(f"Details for {server_detail_data.get('display_hostname', 'N/A')}:{server_detail_data.get('port', 'N/A')}")

        if not server_detail_data or server_detail_data['ping'].startswith('Error'):
            for label_key in detail_labels_ref:
                detail_labels_ref[label_key].config(text="N/A", foreground=ERROR_COLOR)
            for item in detail_player_tree_ref.get_children():
                detail_player_tree_ref.delete(item)
            return

        detail_labels_ref['name'].config(text=f"{server_detail_data.get('display_hostname', 'N/A')}", foreground=DARK_FG)
        detail_labels_ref['ip'].config(text=f"{server_detail_data.get('original_ip', 'N/A')}:{server_detail_data.get('port', 'N/A')}", foreground=DARK_FG)
        ping_fg_color = ERROR_COLOR if server_detail_data.get('ping', '').startswith('Error') else DARK_FG
        detail_labels_ref['ping'].config(text=f"{server_detail_data.get('ping', 'N/A')}", foreground=ping_fg_color)
        detail_labels_ref['map'].config(text=f"{server_detail_data.get('map', 'N/A')}", foreground=DARK_FG)
        detail_labels_ref['mode'].config(text=f"{server_detail_data.get('mode', 'N/A')}", foreground=DARK_FG)
        detail_labels_ref['players_count'].config(text=f"{server_detail_data.get('players_count', 'N/A')}", foreground=DARK_FG)
        detail_labels_ref['spectators_count'].config(text=f"{server_detail_data.get('spectators_count', 'N/A')}", foreground=DARK_FG)


        for item in detail_player_tree_ref.get_children():
            detail_player_tree_ref.delete(item)
        
        self._insert_players_into_tree(detail_player_tree_ref, server_detail_data.get('players', []), simplified_columns=False)


    def _auto_refresh_details_handler(self, server_key):
        if self.stop_event.is_set() or server_key not in self.open_detail_windows or not self.open_detail_windows[server_key]['window'].winfo_exists():
            return
        detail_window_ref = self.open_detail_windows[server_key]['window']
        actual_ip, port = server_key
        Thread(target=self._ping_and_update_detail_modal, args=(server_key, actual_ip, port), name=f"DetailRefresh-{actual_ip}:{port}").start()
        refresh_job_id = detail_window_ref.after(2000, self._auto_refresh_details_handler, server_key) 
        self.open_detail_windows[server_key]['refresh_job_id'] = refresh_job_id


    def _ping_and_update_detail_modal(self, server_key, actual_ip, port):
        err, response, ping_time = udp_command(actual_ip, port, 'status 31\0')
        current_server_data = {}
        initial_display_name = self.server_data.get(server_key, {}).get('display_hostname', "N/A")

        if err:
            current_server_data = {
                'original_ip': actual_ip,
                'display_hostname': initial_display_name,
                'port': port,
                'ping': f"Error: {err['error']}",
                'map': 'N/A',
                'players_count': 'N/A',
                'spectators_count': 'N/A',
                'players': [],
                'mode': 'N/A' 
            }
        else:
            server_info = parse_status_response(response)
            if 'error' in server_info:
                current_server_data = {
                    'original_ip': actual_ip,
                    'display_hostname': initial_display_name,
                    'port': port,
                    'ping': f"Error: {server_info['error']}",
                    'map': 'N/A',
                    'players_count': 'N/A',
                    'spectators_count': 'N/A',
                    'players': [],
                    'mode': 'N/A'
                }
            else:
                hostname_from_server = server_info.get('hostname')
                map_name = server_info.get('map', 'N/A')
                gamemode_from_server = server_info.get('mode', 'N/A')
                resolved_display_name = hostname_from_server if hostname_from_server and hostname_from_server.strip() else initial_display_name
                all_players = server_info.get('players', [])
                spectators = [p for p in all_players if p.get('frags') == 'S']
                players_count = len(all_players) - len(spectators)
                current_server_data = {
                    'original_ip': actual_ip,
                    'display_hostname': resolved_display_name,
                    'port': port,
                    'ping': f"{ping_time:.2f}",
                    'map': map_name,
                    'players_count': players_count,
                    'spectators_count': len(spectators),
                    'players': all_players,
                    'mode': gamemode_from_server
                }
        with self.gui_lock:
            self.server_data[server_key] = current_server_data.copy()
            if server_key in self.favorite_servers_data:
                 self.favorite_servers_data[server_key].update(current_server_data)
        self.gui_queue.put((self._update_detail_view, (server_key, current_server_data), {}))

    def _insert_players_into_tree(self, treeview, players_data, simplified_columns=False):
        actual_players = []
        spectators = []
        for p in players_data:
            if p.get('frags') == 'S':
                spectators.append(p)
            else:
                actual_players.append(p)
        actual_players.sort(key=lambda x: (-x.get('frags', 0) if isinstance(x.get('frags'), int) else 0, x.get('name', '').lower()))
        spectators.sort(key=lambda x: x.get('name', '').lower())

        for index, p in enumerate(actual_players):
            zebra_tag = 'evenrow' if index % 2 == 0 else 'oddrow'
            treeview.insert('', 'end', 
                            values=(p.get('name', 'N/A'), p.get('frags', 'N/A'), p.get('time', 'N/A'), p.get('ping', 'N/A'), p.get('team', 'N/A')),
                            tags=(zebra_tag,))
        for index, p in enumerate(spectators):
            zebra_tag = 'evenrow' if index % 2 == 0 else 'oddrow'
            treeview.insert('', 'end', 
                            values=(p.get('name', 'N/A'), p.get('frags', 'N/A'), p.get('time', 'N/A'), p.get('ping', 'N/A'), p.get('team', 'N/A')),
                            tags=('spectator_row', zebra_tag))


    def _on_tab_select(self, event=None):
        selected_tab_id = self.notebook.select()
        selected_tab_text = self.notebook.tab(selected_tab_id, "text")

        if selected_tab_text == "Players":
            self.player_search_container.grid(row=0, column=0, columnspan=2, sticky='ew', padx=5, pady=5)
            self._apply_player_search_filter()
        else:
            self.player_search_container.grid_forget()

        if selected_tab_text == "Favorites":
            self.remove_from_favorites_button.pack(side='left', padx=5)
        else:
            self.remove_from_favorites_button.pack_forget()


    def show_server_details(self, event):
        current_tab_id = self.notebook.select()
        tree_to_use = None
        items_map = None

        if current_tab_id == self.all_servers_frame._w:
            tree_to_use = self.all_servers_tree
            items_map = self.all_servers_items
        elif current_tab_id == self.favorites_frame._w:
            tree_to_use = self.favorites_tree
            items_map = self.favorites_items
        elif current_tab_id == self.players_frame._w:
            selected_item = self.players_tree.focus()
            if selected_item:
                player_values = self.players_tree.item(selected_item)['values']
                server_name_to_search = player_values[1]
                server_key_to_open = None
                with self.gui_lock:
                    for s_key, s_data in self.server_data.items():
                        if s_data.get('display_hostname') == server_name_to_search:
                            server_key_to_open = s_key
                            break
                if server_key_to_open:
                    self._open_detail_window_for_key(server_key_to_open)
                else:
                    self.gui_queue.put((messagebox.showinfo, ("Server Not Found", f"Could not find server details for '{server_name_to_search}'."), {}))
            return
        
        if tree_to_use and items_map:
            selected_item = tree_to_use.focus()
            if not selected_item:
                return
            found_key = None
            for key, item_id in items_map.items():
                if item_id == selected_item:
                    found_key = key
                    break
            if not found_key:
                self.gui_queue.put((messagebox.showerror, ("Error", "Could not find server details for the selected item."), {}))
                return
            self._open_detail_window_for_key(found_key)
        else:
            return

    def _open_detail_window_for_key(self, server_key):
        if server_key in self.open_detail_windows and self.open_detail_windows[server_key]['window'].winfo_exists():
            self.open_detail_windows[server_key]['window'].lift()
            return

        print(f"Opening new detail window for server {server_key}.")
        detail_window = tk.Toplevel(self.root)
        detail_window.geometry("600x450")
        detail_window.config(bg=DARK_BG)
        detail_window.grab_set()

        initial_display_hostname = self.server_data[server_key].get('display_hostname', 'N/A')
        port = self.server_data[server_key].get('port', 'N/A')
        detail_window.title(f"Details for {initial_display_hostname}:{port}")
        detail_window.transient(self.root)

        info_frame = ttk.Frame(detail_window, style='TFrame')
        info_frame.pack(padx=10, pady=10, fill='x')

        info_frame.columnconfigure(1, weight=1)
        info_frame.columnconfigure(3, weight=1)

        detail_window._detail_labels = {} 
        
        row_idx = 0
        ttk.Label(info_frame, text="Server Name:", style='TLabel').grid(row=row_idx, column=0, sticky='w', padx=2, pady=1)
        detail_window._detail_labels['name'] = ttk.Label(info_frame, text="N/A", anchor='w', style='TLabel')
        detail_window._detail_labels['name'].grid(row=row_idx, column=1, sticky='ew', padx=2, pady=1)

        ttk.Label(info_frame, text="Map:", style='TLabel').grid(row=row_idx, column=2, sticky='w', padx=10, pady=1)
        detail_window._detail_labels['map'] = ttk.Label(info_frame, text="N/A", anchor='w', style='TLabel')
        detail_window._detail_labels['map'].grid(row=row_idx, column=3, sticky='ew', padx=2, pady=1)
        row_idx += 1

        ttk.Label(info_frame, text="IP Address:", style='TLabel').grid(row=row_idx, column=0, sticky='w', padx=2, pady=1)
        detail_window._detail_labels['ip'] = ttk.Label(info_frame, text="N/A", anchor='w', style='TLabel')
        detail_window._detail_labels['ip'].grid(row=row_idx, column=1, sticky='ew', padx=2, pady=1)

        ttk.Label(info_frame, text="Mode:", style='TLabel').grid(row=row_idx, column=2, sticky='w', padx=10, pady=1)
        detail_window._detail_labels['mode'] = ttk.Label(info_frame, text="N/A", anchor='w', style='TLabel')
        detail_window._detail_labels['mode'].grid(row=row_idx, column=3, sticky='ew', padx=2, pady=1)
        row_idx += 1

        ttk.Label(info_frame, text="Ping:", style='TLabel').grid(row=row_idx, column=0, sticky='w', padx=2, pady=1)
        detail_window._detail_labels['ping'] = ttk.Label(info_frame, text="N/A", anchor='w', style='TLabel')
        detail_window._detail_labels['ping'].grid(row=row_idx, column=1, sticky='ew', padx=2, pady=1)

        ttk.Label(info_frame, text="Players:", style='TLabel').grid(row=row_idx, column=2, sticky='w', padx=10, pady=1)
        detail_window._detail_labels['players_count'] = ttk.Label(info_frame, text="N/A", anchor='w', style='TLabel')
        detail_window._detail_labels['players_count'].grid(row=row_idx, column=3, sticky='ew', padx=2, pady=1)
        row_idx += 1

        ttk.Label(info_frame, text="Spectators:", style='TLabel').grid(row=row_idx, column=2, sticky='w', padx=10, pady=1)
        detail_window._detail_labels['spectators_count'] = ttk.Label(info_frame, text="N/A", anchor='w', style='TLabel')
        detail_window._detail_labels['spectators_count'].grid(row=row_idx, column=3, sticky='ew', padx=2, pady=1)
        
        refresh_interval_milliseconds = 2000 
        refresh_interval_seconds = refresh_interval_milliseconds / 1000
        ttk.Label(info_frame, text=f"Auto-refresh: {refresh_interval_seconds:.0f} seconds", 
                  font=('TkDefaultFont', 8, 'italic'), foreground=DARK_FG, anchor='w', style='TLabel').grid(row=row_idx + 1, column=0, columnspan=4, sticky='ew', padx=2, pady=5)


        content_frame = ttk.Frame(detail_window, style='TFrame')
        content_frame.pack(padx=10, pady=5, fill='both', expand=True)
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(1, weight=1) 

        
        ttk.Label(content_frame, text="Players on server:", style='TLabel').grid(row=0, column=0, sticky='w', pady=(5,2))

        detail_window._detail_player_tree = ttk.Treeview(content_frame,
                                               columns=('Name', 'Frags', 'Time', 'Ping', 'Team'),
                                               show='headings',
                                               height=8,
                                               style='Treeview')
        
        detail_window._detail_player_tree.tag_configure('spectator_row', background=SPECTATOR_BG, foreground=DARK_FG)
        detail_window._detail_player_tree.tag_configure('oddrow', background=ODD_ROW_BG, foreground=DARK_FG)
        detail_window._detail_player_tree.tag_configure('evenrow', background=EVEN_ROW_BG, foreground=DARK_FG)


        detail_window._detail_player_tree.heading('Name', text='Name')
        detail_window._detail_player_tree.column('Name', width=160, anchor='w')
        detail_window._detail_player_tree.heading('Frags', text='Frags')
        detail_window._detail_player_tree.column('Frags', width=45, anchor='center')
        detail_window._detail_player_tree.heading('Time', text='Time')
        detail_window._detail_player_tree.column('Time', width=45, anchor='center')
        detail_window._detail_player_tree.heading('Ping', text='Ping')
        detail_window._detail_player_tree.column('Ping', width=45, anchor='center')
        detail_window._detail_player_tree.heading('Team', text='Team')
        detail_window._detail_player_tree.column('Team', width=80, anchor='center')
        
        detail_window._detail_player_tree.grid(row=1, column=0, sticky='nsew', pady=(0, 5))

        detail_player_scrollbar = ttk.Scrollbar(content_frame, orient='vertical', command=detail_window._detail_player_tree.yview)
        detail_window._detail_player_tree.configure(yscrollcommand=detail_player_scrollbar.set)
        detail_player_scrollbar.grid(row=1, column=1, sticky='ns', pady=(0, 5))


        initial_server_data = self.server_data.get(server_key, {}) 
        self._update_detail_view(server_key, initial_server_data)
        
        actual_ip, port = server_key
        Thread(target=self._ping_and_update_detail_modal, args=(server_key, actual_ip, port), name=f"ImmediateDetailPing-{actual_ip}:{port}").start()
        
        refresh_job_id = detail_window.after(2000, self._auto_refresh_details_handler, server_key) 
        
        self.open_detail_windows[server_key] = {
            'window': detail_window,
            'refresh_job_id': refresh_job_id
        }
        detail_window.protocol("WM_DELETE_WINDOW", lambda: self._on_detail_window_closing_handler(server_key))


    def _start_drag_window(self, event, window):
        window._offset_x = event.x
        window._offset_y = event.y

    def _drag_window(self, event, window):
        x = window.winfo_x() + event.x - window._offset_x
        y = window.winfo_y() + event.y - window._offset_y
        window.geometry(f"+{x}+{y}")


    def update_server_display(self, server_key, values_for_treeview):
        if self.stop_event.is_set():
            return
        if self.root.winfo_exists():
            with self.gui_lock:
                item_id_all = self.all_servers_items.get(server_key)
                if item_id_all:
                    current_tags_all = list(self.all_servers_tree.item(item_id_all, 'tags'))
                    new_ping_tag = self._get_ping_color_tag(values_for_treeview[2])
                    
                    current_tags_all = [tag for tag in current_tags_all if not tag.startswith('ping_')]
                    current_tags_all.append(new_ping_tag)

                    self.all_servers_tree.item(item_id_all, values=values_for_treeview, image='', tags=tuple(current_tags_all))
                
                item_id_fav = self.favorites_items.get(server_key)
                if item_id_fav:
                    current_tags_fav = list(self.favorites_tree.item(item_id_fav, 'tags'))
                    new_ping_tag = self._get_ping_color_tag(values_for_treeview[2])

                    current_tags_fav = [tag for tag in current_tags_fav if not tag.startswith('ping_')]
                    current_tags_fav.append(new_ping_tag)

                    self.favorites_tree.item(item_id_fav, values=values_for_treeview, image='', tags=tuple(current_tags_fav))
        else:
            pass


def main():
    print(f"Application starting with Python executable: {sys.executable}")
    root = tk.Tk()
    root.geometry("850x550")
    app = QuakeWorldGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()  