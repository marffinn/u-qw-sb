import socket
import time
import tkinter as tk
from tkinter import ttk, messagebox
import re
from threading import Thread, Lock, Event
import subprocess
from PIL import Image, ImageTk, ImageDraw
import os
import json


# Constants
UDP_TIMEOUT = 3.0
FAVORITES_FILE = 'favorites.json' # File to save/load favorite servers

CHARSET = {
    0: 46,  # .
    1: 35,  # #
    2: 35,
    3: 35,
    4: 35,
    5: 46,
    6: 35,
    7: 35,
    8: 35,
    9: 35,
    11: 35,
    12: 32,  # SPACE
    13: 62,  # >
    14: 46,
    15: 46,
    16: 91,  # [
    17: 93,  # ]
    18: 48,  # 0
    19: 49,  # 1
    20: 50,  # 2
    21: 51,  # 3
    22: 52,  # 4
    23: 53,  # 5
    24: 54,  # 6
    25: 55,  # 7
    26: 56,  # 8
    27: 57,  # 9
    28: 46,
    29: 32,
    30: 32,
    31: 32,
    127: 32,
    128: 40,  # (
    129: 61,  # =
    130: 41,  # )
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

# --- Dark Theme Colors ---
DARK_BG = '#282c34' # A dark gray background
DARK_FG = '#abb2bf' # A light gray foreground
ACCENT_COLOR = '#61afef' # A blue accent color for highlights
BUTTON_BG = '#3e4451' # Darker gray for buttons
BUTTON_FG = DARK_FG
SELECTED_BG = '#4b5263' # Background for selected items
ERROR_COLOR = '#e06c75' # Red for errors
SPECTATOR_BG = '#3e4451' # Darker background for spectators

# --- Quake 1 Player Color Palette (hardcoded as requested) ---
QUAKE_COLOR_RGB_PALETTE = {
    0: (153, 153, 153),
    1: (102, 73, 33),
    2: (89, 89, 130),
    3: (78, 78, 10),
    4: (97, 0, 0),
    5: (119, 89, 9),
    6: (162, 76, 58),
    7: (144, 94, 71),
    8: (103, 65, 79),
    9: (112, 60, 74),
    10: (122, 99, 81),
    11: (58, 82, 67),
    12: (147, 118, 8),
    13: (54, 54, 146),
    14: (207, 58, 17),
    15: (129, 0, 0),
    16: (13, 13, 13),
}


def quake_chars(data):
    """Convert QuakeWorld-specific characters to standard ASCII, matching quakeworld.js."""
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
    """Send a UDP command to the QuakeWorld server, matching quakeworld.js."""
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(UDP_TIMEOUT)
        buf = b'\xFF\xFF\xFF\xFF' + data.encode('ascii')
        send_time = time.time()
        client.sendto(buf, (address, port))
        msg, _ = client.recvfrom(4096)
        ping_time = (time.time() - send_time) * 1000  # Convert to milliseconds
        client.close()
        
        return None, msg, ping_time
    except socket.timeout:
        client.close()
        return {"error": "timeout"}, None, None
    except socket.error as e:
        client.close()
        return {"error": str(e)}, None, None


def parse_status_response(data):
    """Parse the status response from a QuakeWorld server, matching cmd.status."""
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

                if value_candidate == 'hostname' and 'hostname' not in server_info:
                    server_info['hostname'] = key_candidate
                    i += 2
                    continue
                elif value_candidate == 'map' and 'map' not in server_info:
                    server_info['map'] = key_candidate
                    i += 2
                    continue
                elif value_candidate == 'mode' and 'mode' not in server_info:
                    server_info['mode'] = key_candidate
                    i += 2
                    continue
                
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
                
                try:
                    server_info[key_candidate] = value_candidate if isNaN(value_candidate) else int(value_candidate)
                except ValueError: 
                    pass
                
                i += 2

            if i < len(tmp_parts):
                 pass

        for p_line in lines:
            if not p_line.strip():
                continue
            
            match = re.match(
                r'^(-?\d+)\s+(-?[S\d]+)\s+(-?\d+)\s+(-?\d+)\s*\s*"(.*?)"\s*"(.*?)"\s*(\d+)\s*(\d+)(?:\s"(.*?)"|$)', p_line)

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
                except (ValueError, TypeError) as e:
                    print(f"Warning: Failed to convert player data types for line: '{p_line}' - {e}")
            else:
                print(f"Warning: Failed to parse player line with new regex: '{p_line}'")

        server_info['players'] = players
        
        return server_info
    except Exception as e:
        print(f"Error in parse_status_response: {e}")
        return {"error": f"parse error: {str(e)}"}


def isNaN(value):
    """Check if a value is not a number, matching JavaScript isNaN."""
    try:
        int(value)
        return False
    except ValueError:
        return True


def read_servers(file_path='eu-sv.txt'):
    """Read server list from file and prepend qw.servegame.org.
    Filters out servers with port 30000.
    Returns a list of tuples: (initial_display_name, port, actual_ip).
    """
    servers = []
    
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
                        actual_ip = socket.gethostbyname(address_or_hostname)
                        servers.append((address_or_hostname, port, actual_ip)) 
                    except socket.gaierror:
                        print(f"Warning: Could not resolve address/hostname '{address_or_hostname}'. Skipping.")
    except FileNotFoundError:
        print(f"Error: {file_path} not found")
    return servers


class QuakeWorldGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("QuakeWorld Server Pinger")
        self.servers = read_servers()
        self.sort_column = None
        self.sort_reverse = False
        self.server_data = {}  # All known servers, including favorites
        self.favorite_servers_data = {} # Only servers marked as favorite
        self.gui_lock = Lock()
        self.stop_event = Event()

        self.open_detail_windows = {} 

        # No need to load_quake_colors() anymore, palette is hardcoded.

        self._apply_dark_theme()
        self._load_favorites() # Load favorites after theme is applied

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        # --- Notebook for tabs ---
        self.notebook = ttk.Notebook(root)
        self.notebook.grid(row=0, column=0, columnspan=2, sticky='nsew', padx=5, pady=5)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # --- "All Servers" Tab ---
        self.all_servers_frame = ttk.Frame(self.notebook, style='TFrame')
        self.notebook.add(self.all_servers_frame, text='All Servers')

        self.all_servers_tree = ttk.Treeview(self.all_servers_frame, columns=('Name', 'Port', 'Ping', 'Map', 'Players', 'Spectators'),
                                 show='headings', style='Treeview')
        self.all_servers_tree.heading('Name', text='Server Name / Address', command=lambda: self.sort_column_by('Name', self.all_servers_tree))
        self.all_servers_tree.heading('Port', text='Port', command=lambda: self.sort_column_by('Port', self.all_servers_tree))
        self.all_servers_tree.heading('Ping', text='Ping (ms)', command=lambda: self.sort_column_by('Ping', self.all_servers_tree))
        self.all_servers_tree.heading('Map', text='Map', command=lambda: self.sort_column_by('Map', self.all_servers_tree))
        self.all_servers_tree.heading('Players', text='Players', command=lambda: self.sort_column_by('Players', self.all_servers_tree))
        self.all_servers_tree.heading('Spectators', text='Spectators', command=lambda: self.sort_column_by('Spectators', self.all_servers_tree))
        
        self.all_servers_tree.column('Name', width=150)
        self.all_servers_tree.column('Port', width=60)
        self.all_servers_tree.column('Ping', width=70)
        self.all_servers_tree.column('Map', width=100)
        self.all_servers_tree.column('Players', width=60)
        self.all_servers_tree.column('Spectators', width=80)

        all_servers_scrollbar = ttk.Scrollbar(self.all_servers_frame, orient='vertical', command=self.all_servers_tree.yview)
        self.all_servers_tree.configure(yscrollcommand=all_servers_scrollbar.set)

        self.all_servers_tree.grid(row=0, column=0, sticky='nsew')
        all_servers_scrollbar.grid(row=0, column=1, sticky='ns')
        self.all_servers_tree.bind("<Double-1>", self.show_server_details)
        self.all_servers_frame.grid_rowconfigure(0, weight=1)
        self.all_servers_frame.grid_columnconfigure(0, weight=1)

        # --- "Favorites" Tab ---
        self.favorites_frame = ttk.Frame(self.notebook, style='TFrame')
        self.notebook.add(self.favorites_frame, text='Favorites')

        self.favorites_tree = ttk.Treeview(self.favorites_frame, columns=('Name', 'Port', 'Ping', 'Map', 'Players', 'Spectators'),
                                show='headings', style='Treeview')
        self.favorites_tree.heading('Name', text='Server Name / Address', command=lambda: self.sort_column_by('Name', self.favorites_tree))
        self.favorites_tree.heading('Port', text='Port', command=lambda: self.sort_column_by('Port', self.favorites_tree))
        self.favorites_tree.heading('Ping', text='Ping (ms)', command=lambda: self.sort_column_by('Ping', self.favorites_tree))
        self.favorites_tree.heading('Map', text='Map', command=lambda: self.sort_column_by('Map', self.favorites_tree))
        self.favorites_tree.heading('Players', text='Players', command=lambda: self.sort_column_by('Players', self.favorites_tree))
        self.favorites_tree.heading('Spectators', text='Spectators', command=lambda: self.sort_column_by('Spectators', self.favorites_tree))

        self.favorites_tree.column('Name', width=150)
        self.favorites_tree.column('Port', width=60)
        self.favorites_tree.column('Ping', width=70)
        self.favorites_tree.column('Map', width=100)
        self.favorites_tree.column('Players', width=60)
        self.favorites_tree.column('Spectators', width=80)
        
        favorites_scrollbar = ttk.Scrollbar(self.favorites_frame, orient='vertical', command=self.favorites_tree.yview)
        self.favorites_tree.configure(yscrollcommand=favorites_scrollbar.set)

        self.favorites_tree.grid(row=0, column=0, sticky='nsew')
        favorites_scrollbar.grid(row=0, column=1, sticky='ns')
        self.favorites_tree.bind("<Double-1>", self.show_server_details)
        self.favorites_frame.grid_rowconfigure(0, weight=1)
        self.favorites_frame.grid_columnconfigure(0, weight=1)

        # --- Buttons and Ping Threshold Input ---
        button_frame = ttk.Frame(root, style='TFrame')
        button_frame.grid(row=1, column=0, columnspan=2, pady=10) # Position below notebook

        ttk.Button(button_frame, text="Ping All Servers", command=self.ping_all, style='TButton').pack(side='left', padx=5)
        ttk.Button(button_frame, text="Connect to Selected Server", command=self.connect_selected, style='TButton').pack(side='left', padx=5)
        ttk.Button(button_frame, text="Add to Favorites", command=self._add_to_favorites_action, style='TButton').pack(side='left', padx=5)
        ttk.Button(button_frame, text="Remove from Favorites", command=self._remove_from_favorites_action, style='TButton').pack(side='left', padx=5)

        ttk.Label(button_frame, text="Max Ping (ms):", style='TLabel').pack(side='left', padx=5)
        self.ping_threshold_var = tk.StringVar(value="")
        self.ping_threshold_entry = ttk.Entry(button_frame, textvariable=self.ping_threshold_var, width=10, style='TEntry')
        self.ping_threshold_entry.pack(side='left', padx=5)
        self.ping_threshold_entry.bind("<KeyRelease>", self._on_ping_threshold_change)
        
        # Initial population of all_servers_tree
        self.all_servers_items = {} # Renamed from self.server_items
        for initial_display_name, port, actual_ip in self.servers:
            server_key = (actual_ip, port)
            item_id = self.all_servers_tree.insert('', 'end', values=(initial_display_name, port, 'N/A', 'N/A', 'N/A', 'N/A'))
            self.all_servers_items[server_key] = item_id
            # Also ensure server_data holds initial data for these.
            if server_key not in self.server_data:
                self.server_data[server_key] = {
                    'original_ip': actual_ip,
                    'display_hostname': initial_display_name,
                    'port': port,
                    'ping': 'N/A', 'map': 'N/A', 'players_count': 'N/A',
                    'spectators_count': 'N/A', 'players': [], 'mode': 'N/A'
                }
        
        # Populate the favorites tree with loaded data
        self.favorites_items = {} # New mapping for favorites tree
        self._update_favorites_tree_display()


    def _apply_dark_theme(self):
        s = ttk.Style()
        s.theme_use('clam')

        self.root.config(bg=DARK_BG)

        s.configure('.', background=DARK_BG, foreground=DARK_FG, bordercolor=DARK_BG)
        s.configure('TFrame', background=DARK_BG, foreground=DARK_FG, bordercolor=DARK_BG)
        s.configure('TLabel', background=DARK_BG, foreground=DARK_FG)
        s.configure('TButton', background=BUTTON_BG, foreground=BUTTON_FG, borderwidth=1, focusthickness=3, focuscolor=ACCENT_COLOR)
        s.map('TButton', background=[('active', ACCENT_COLOR)])
        s.configure('TEntry', fieldbackground=BUTTON_BG, foreground=DARK_FG, insertcolor=DARK_FG, bordercolor=ACCENT_COLOR)

        # --- Treeview styling to remove all borders ---
        s.configure('Treeview',
                    background=DARK_BG,
                    foreground=DARK_FG,
                    fieldbackground=DARK_BG,
                    borderwidth=0,          # Remove outer border of the Treeview
                    highlightthickness=0,   # Remove focus highlight border
                    relief='flat'           # Ensure flat relief
                   )
        s.map('Treeview', background=[('selected', SELECTED_BG)], foreground=[('selected', DARK_FG)])
        
        # --- Treeview Heading styling to remove all borders ---
        s.configure('Treeview.Heading',
                    background=BUTTON_BG,
                    foreground=DARK_FG,
                    font=('TkDefaultFont', 10, 'bold'),
                    borderwidth=0,          # Remove borders between headings and around heading area
                    highlightthickness=0,   # Remove focus highlight border for headings
                    relief='flat'           # Ensure flat relief for headings
                   )
        s.map('Treeview.Heading', background=[('active', ACCENT_COLOR)])

        s.configure("Vertical.TScrollbar", background=BUTTON_BG, troughcolor=DARK_BG, bordercolor=DARK_BG, arrowcolor=DARK_FG)
        s.map("Vertical.TScrollbar", background=[('active', ACCENT_COLOR)], arrowcolor=[('active', DARK_FG)])

        # Notebook tab styling
        s.configure('TNotebook', background=DARK_BG, borderwidth=0)
        s.configure('TNotebook.Tab', background=BUTTON_BG, foreground=DARK_FG, borderwidth=0)
        s.map('TNotebook.Tab', background=[('selected', ACCENT_COLOR)], foreground=[('selected', DARK_BG)])


        self.root.option_add("*background", DARK_BG)
        self.root.option_add("*foreground", DARK_FG)
        self.root.option_add("*Toplevel.background", DARK_BG)

    def _load_favorites(self):
        """Loads favorite servers from favorites.json."""
        try:
            with open(FAVORITES_FILE, 'r') as f:
                loaded_favorites_list = json.load(f)
                self.favorite_servers_data = {}
                for fav_server_info in loaded_favorites_list:
                    # Reconstruct key and add to data structures
                    ip = fav_server_info['original_ip']
                    port = fav_server_info['port']
                    server_key = (ip, port)
                    self.favorite_servers_data[server_key] = fav_server_info
                    # Ensure favorite server is also in the main server_data so ping_all finds it
                    # Merge existing data if available to keep it up to date or add new fav server
                    if server_key in self.server_data:
                        self.server_data[server_key].update(fav_server_info)
                    else:
                        self.server_data[server_key] = fav_server_info
        except FileNotFoundError:
            print(f"'{FAVORITES_FILE}' not found. Starting with empty favorites.")
            self.favorite_servers_data = {}
        except json.JSONDecodeError as e:
            print(f"Error reading favorites file: {e}. Starting with empty favorites.")
            self.favorite_servers_data = {}

    def _save_favorites(self):
        """Saves current favorite servers to favorites.json."""
        # Convert dictionary values (server_info dicts) to a list for JSON serialization
        # Only save fields that are JSON serializable.
        serializable_favorites = []
        for server_info in self.favorite_servers_data.values():
            # Exclude non-serializable fields if any, or prepare for simple dump
            serializable_favorites.append(server_info) 
        
        with open(FAVORITES_FILE, 'w') as f:
            json.dump(serializable_favorites, f, indent=2)

    def _on_closing(self):
        """Handle main window closing event."""
        print("Closing application. Signaling threads to stop.")
        self.stop_event.set()
        self._save_favorites() # Save favorites before closing
        for server_key in list(self.open_detail_windows.keys()):
            self._on_detail_window_closing_handler(server_key)
        self.root.destroy()

    def sort_column_by(self, col, treeview):
        """Sort the given Treeview by the specified column."""
        with self.gui_lock:
            # This sorting is applied to whichever treeview is passed in
            items = [(treeview.item(item)['values'], item) for item in treeview.get_children()]
            col_index = {'Name': 0, 'Port': 1, 'Ping': 2, 'Map': 3, 'Players': 4, 'Spectators': 5}[col]

            def sort_key(item):
                value = item[0][col_index]
                if col == 'Port':
                    try:
                        return int(value)
                    except ValueError:
                        return float('inf') # Treat non-numeric values as largest for sorting
                elif col == 'Ping':
                    try:
                        return float(value.split()[0]) # Handle "XX.XX" vs "Error: ..."
                    except (ValueError, IndexError):
                        return float('inf') # Treat errors/N/A as largest
                elif col == 'Players' or col == 'Spectators':
                    try:
                        return int(value)
                    except ValueError:
                        return -1 # Treat non-numeric as smallest (at bottom for counts)
                return str(value).lower()

            items.sort(key=sort_key, reverse=self.sort_reverse)
            for index, (_, item) in enumerate(items):
                treeview.move(item, '', index)

            # Toggle sort_reverse for the next click on the same column
            if self.sort_column == col:
                self.sort_reverse = not self.sort_reverse
            else:
                self.sort_column = col
                self.sort_reverse = False


    def ping_server(self, initial_display_name, port, actual_ip):
        """Ping a single server and update GUI, using status 31 for detailed info."""
        if self.stop_event.is_set():
            return

        server_key = (actual_ip, port)
        err, response, ping_time = udp_command(actual_ip, port, 'status 31\0')
        
        current_server_data = {}

        if err:
            values_for_treeview = (initial_display_name, port, f"Error: {err['error']}", 'N/A', 'N/A', 'N/A')
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
                values_for_treeview = (initial_display_name, port, f"Error: {server_info['error']}", 'N/A', 'N/A', 'N/A')
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
                
                values_for_treeview = (resolved_display_name, port, f"{ping_time:.2f}", map_name, players_count, len(spectators))
                
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
            self.server_data[server_key] = current_server_data
            # If this server is a favorite, update its entry in favorite_servers_data as well
            if server_key in self.favorite_servers_data:
                # Ensure existing favorite flags are preserved if any, only update dynamic data
                self.favorite_servers_data[server_key].update(current_server_data)

            if server_key in self.open_detail_windows:
                 self.root.after(0, self._update_detail_view, server_key, current_server_data)

        self.root.after(0, self.update_server_display, server_key, values_for_treeview)


    def ping_all(self):
        """Ping all known servers (from file and favorites) in separate threads."""
        
        all_servers_to_ping = []
        
        # Add servers from eu-sv.txt list
        for initial_display_name, port, actual_ip in self.servers:
            all_servers_to_ping.append((initial_display_name, port, actual_ip))

        # Add unique favorite servers that are not already in the main list
        # We ensure to use the most up-to-date 'display_hostname' from `server_data` for consistency
        for fav_key, fav_data in self.favorite_servers_data.items():
            # Check if this favorite server's (ip, port) is NOT already represented in `all_servers_to_ping`
            if not any(s_ip == fav_key[0] and s_port == fav_key[1] for _, s_port, s_ip in all_servers_to_ping):
                 # Use data from `self.server_data` if available, otherwise `fav_data` (initial loaded state)
                source_for_ping = self.server_data.get(fav_key, fav_data)
                all_servers_to_ping.append((source_for_ping['display_hostname'], source_for_ping['port'], source_for_ping['original_ip']))


        def thread_func():
            for initial_display_name, port, actual_ip in all_servers_to_ping:
                if self.stop_event.is_set():
                    print("Ping-all thread received stop signal.")
                    break
                self.ping_server(initial_display_name, port, actual_ip) 
            print("Ping-all thread finished.")
            self.root.after(0, self.sort_by_ping_and_players)

        # Clear existing server data for a fresh ping, and reset Treeview displays
        with self.gui_lock:
            for key in self.server_data:
                self.server_data[key].update({
                    'ping': 'N/A', 'map': 'N/A', 'players_count': 'N/A',
                    'spectators_count': 'N/A', 'players': [], 'mode': 'N/A'
                })
            # Also reset favorites data's ping values (it points to server_data entries, so updating server_data updates favorites_data implicitly if they share ref)
            # If favorite_servers_data stores copies, explicitly update its ping info
            for key in self.favorite_servers_data:
                 self.favorite_servers_data[key].update({
                    'ping': 'N/A', 'map': 'N/A', 'players_count': 'N/A',
                    'spectators_count': 'N/A', 'players': [], 'mode': 'N/A'
                })

            # Clear both treeviews and their item mappings
            self.all_servers_tree.delete(*self.all_servers_tree.get_children())
            self.all_servers_items = {}
            self.favorites_tree.delete(*self.favorites_tree.get_children())
            self.favorites_items = {}

            # Re-populate initial N/A entries for both trees
            self._populate_initial_treeview(self.all_servers_tree, self.servers, self.all_servers_items, self.server_data)
            # For favorites tree, use the current `self.favorite_servers_data` (which now has 'N/A' pings)
            self._populate_initial_treeview(self.favorites_tree, [(v['display_hostname'], v['port'], v['original_ip']) for v in self.favorite_servers_data.values()], self.favorites_items, self.favorite_servers_data)

        Thread(target=thread_func).start()

    def _populate_initial_treeview(self, treeview_widget, server_list_source, items_map_target, data_source_dict):
        """Helper to (re-)populate a specific treeview with initial 'N/A' data or current data."""
        for initial_display_name, port, actual_ip in server_list_source:
            server_key = (actual_ip, port)
            data = data_source_dict.get(server_key, {
                'original_ip': actual_ip,
                'display_hostname': initial_display_name,
                'port': port,
                'ping': 'N/A', 'map': 'N/A', 'players_count': 'N/A',
                'spectators_count': 'N/A', 'players': [], 'mode': 'N/A'
            })
            values = (data['display_hostname'], data['port'], data['ping'], data['map'], data['players_count'], data['spectators_count'])
            item_id = treeview_widget.insert('', 'end', values=values)
            items_map_target[server_key] = item_id


    def sort_by_ping_and_players(self):
        """Sorts and filters both Treeviews by ping and players, applying ping threshold."""
        with self.gui_lock:
            ping_threshold_str = self.ping_threshold_var.get().strip()
            ping_threshold = float('inf')

            if ping_threshold_str:
                try:
                    ping_threshold = float(ping_threshold_str)
                except ValueError:
                    messagebox.showwarning("Invalid Input", "Please enter a valid number for Max Ping.")
                    self.ping_threshold_var.set("")
                    # Re-display all currently known servers if input is invalid
                    self._repopulate_all_trees(filter_by_ping=False)
                    return


            self._repopulate_all_trees(filter_by_ping=True, ping_threshold=ping_threshold)


    def _repopulate_all_trees(self, filter_by_ping=False, ping_threshold=float('inf')):
        """Helper to clear and repopulate both Treeviews with optional ping filtering."""

        # --- Repopulate All Servers Tree ---
        self.all_servers_tree.delete(*self.all_servers_tree.get_children())
        self.all_servers_items = {}

        displayable_all_servers = []
        for (ip, port), data in self.server_data.items():
            # Only consider servers that originated from eu-sv.txt for the "All Servers" tab
            is_from_initial_list = any(s_ip == ip and s_p == port for _, s_p, s_ip in self.servers)
            if not is_from_initial_list:
                continue # Skip if this server only exists in server_data because it's a favorite

            try:
                ping_val_str = data['ping']
                ping_value = float('inf')
                if not ("Error" in ping_val_str or ping_val_str == 'N/A'):
                    ping_value = float(ping_val_str)
                        
                players_count_val = data['players_count']
                players_count = -1
                if players_count_val != 'N/A':
                    players_count = int(players_count_val)
                    
                if not filter_by_ping or ping_value <= ping_threshold:
                    displayable_all_servers.append((ping_value, players_count, ip, port, data))
            except (ValueError, TypeError, IndexError):
                if not filter_by_ping: # If no filter, show even if data is broken
                    displayable_all_servers.append((float('inf'), -1, ip, port, data))
        
        displayable_all_servers.sort(key=lambda x: (x[0], -x[1]))
        for ping_value, players_count, ip, port, data in displayable_all_servers:
            values = (data['display_hostname'], data['port'], data['ping'], data['map'], data['players_count'], data['spectators_count'])
            item_id = self.all_servers_tree.insert('', 'end', values=values)
            self.all_servers_items[(ip, port)] = item_id


        # --- Repopulate Favorites Tree ---
        self.favorites_tree.delete(*self.favorites_tree.get_children())
        self.favorites_items = {}

        displayable_favorites = []
        for (ip, port), data in self.favorite_servers_data.items():
            try:
                ping_val_str = data['ping']
                ping_value = float('inf')
                if not ("Error" in ping_val_str or ping_val_str == 'N/A'):
                    ping_value = float(ping_val_str)
                        
                players_count_val = data['players_count']
                players_count = -1
                if players_count_val != 'N/A':
                    players_count = int(players_count_val)
                    
                if not filter_by_ping or ping_value <= ping_threshold:
                    displayable_favorites.append((ping_value, players_count, ip, port, data))
            except (ValueError, TypeError, IndexError):
                if not filter_by_ping: # If no filter, show even if data is broken
                    displayable_favorites.append((float('inf'), -1, ip, port, data))
        
        displayable_favorites.sort(key=lambda x: (x[0], -x[1]))
        for ping_value, players_count, ip, port, data in displayable_favorites:
            values = (data['display_hostname'], data['port'], data['ping'], data['map'], data['players_count'], data['spectators_count'])
            item_id = self.favorites_tree.insert('', 'end', values=values)
            self.favorites_items[(ip, port)] = item_id


    def _on_ping_threshold_change(self, event=None):
        """Called when the ping threshold entry changes. Triggers a re-sort/re-filter."""
        self.root.after(100, self.sort_by_ping_and_players)


    def _add_to_favorites_action(self):
        """Adds the selected server from the 'All Servers' tab to favorites."""
        selected_item = self.all_servers_tree.focus()
        if not selected_item:
            messagebox.showinfo("Add to Favorites", "Please select a server to add to favorites.")
            return

        selected_server_key = None
        for key, item_id in self.all_servers_items.items():
            if item_id == selected_item:
                selected_server_key = key
                break
        
        if selected_server_key:
            if selected_server_key not in self.favorite_servers_data:
                # Add a copy of the server_info to favorites
                # We fetch current info from `self.server_data` for fresh details
                self.favorite_servers_data[selected_server_key] = self.server_data.get(selected_server_key, {}).copy()
                if not self.favorite_servers_data[selected_server_key]: # Fallback if for some reason not in server_data
                    messagebox.showerror("Error", "Server data not found to add to favorites.")
                    return
                self._update_favorites_tree_display()
                self._save_favorites()
                messagebox.showinfo("Add to Favorites", f"Added {self.favorite_servers_data[selected_server_key].get('display_hostname', 'Unknown')}:{selected_server_key[1]} to favorites.")
            else:
                messagebox.showinfo("Add to Favorites", "This server is already in your favorites.")
        else:
            messagebox.showerror("Error", "Could not identify the selected server.")

    def _remove_from_favorites_action(self):
        """Removes the selected server from the 'Favorites' tab."""
        selected_item = self.favorites_tree.focus()
        if not selected_item:
            messagebox.showinfo("Remove from Favorites", "Please select a server to remove from favorites.")
            return

        selected_server_key = None
        for key, item_id in self.favorites_items.items():
            if item_id == selected_item:
                selected_server_key = key
                break
        
        if selected_server_key:
            if selected_server_key in self.favorite_servers_data:
                del self.favorite_servers_data[selected_server_key]
                self._update_favorites_tree_display()
                self._save_favorites()
                messagebox.showinfo("Remove from Favorites", f"Removed {selected_server_key[0]}:{selected_server_key[1]} from favorites.")
            else:
                messagebox.showwarning("Remove from Favorites", "This server is not in your favorites.")
        else:
            messagebox.showerror("Error", "Could not identify the selected server.")

    def _update_favorites_tree_display(self):
        """Clears and repopulates the favorites treeview."""
        self.favorites_tree.delete(*self.favorites_tree.get_children())
        self.favorites_items = {} # Clear item ID map
        
        # Repopulate using current data from self.favorite_servers_data
        displayable_favorites = []
        for key, data in self.favorite_servers_data.items():
            # Apply potential ping filter if active, similar to sort_by_ping_and_players
            ping_threshold_str = self.ping_threshold_var.get().strip()
            ping_threshold = float('inf')
            if ping_threshold_str:
                try:
                    ping_threshold = float(ping_threshold_str)
                except ValueError:
                    pass
            
            try:
                ping_val_str = data['ping']
                ping_value = float('inf')
                if not ("Error" in ping_val_str or ping_val_str == 'N/A'):
                    ping_value = float(ping_val_str)
                        
                if ping_value <= ping_threshold:
                    displayable_favorites.append(data)
            except (ValueError, TypeError, IndexError):
                if not ping_threshold_str:
                     displayable_favorites.append(data)

        displayable_favorites.sort(key=lambda x: str(x.get('display_hostname', '')).lower())

        for data in displayable_favorites:
            server_key = (data['original_ip'], data['port'])
            values = (data['display_hostname'], data['port'], data['ping'], data['map'], data['players_count'], data['spectators_count'])
            item_id = self.favorites_tree.insert('', 'end', values=values)
            self.favorites_items[server_key] = item_id


    def connect_selected(self):
        """Connect to the selected server from either active tab."""
        # Determine which tree is active
        current_tab_id = self.notebook.select()
        if current_tab_id == self.all_servers_frame._w:
            tree_to_use = self.all_servers_tree
            items_map = self.all_servers_items
        elif current_tab_id == self.favorites_frame._w:
            tree_to_use = self.favorites_tree
            items_map = self.favorites_items
        else:
            messagebox.showerror("Error", "No active server list found.")
            return

        selected_item = tree_to_use.focus()
        if not selected_item:
            messagebox.showinfo("Connect to Server", "Please select a server to connect to.")
            return

        found_key = None
        for key, item_id in items_map.items():
            if item_id == selected_item:
                found_key = key
                break
            
        if found_key:
            actual_ip, port = found_key
            self.connect_to_server(actual_ip, port)
        else:
            messagebox.showerror("Error", "Could not identify the selected server for connection.")


    def connect_to_server(self, address, port):
        """Launch the QuakeWorld client and connect to the specified server."""
        client_exec = "ezquake-gl.exe" # Hardcoded default executable
        command = [client_exec, f"+connect {address}:{port}"]
        try:
            subprocess.Popen(command, shell=True)
            messagebox.showinfo("Launch Client", f"Attempting to connect to {address}:{port} with '{client_exec}'...")
        except FileNotFoundError:
            messagebox.showerror("Error", f"QuakeWorld client executable not found. Please ensure '{client_exec}' is in your system's PATH or the application directory.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch QuakeWorld client: {e}")

    def _on_detail_window_closing_handler(self, server_key):
        """Handles closing of a specific detail window."""
        if server_key in self.open_detail_windows:
            detail_info = self.open_detail_windows[server_key]
            if detail_info['window'].winfo_exists():
                if detail_info['refresh_job_id'] is not None:
                    detail_info['window'].after_cancel(detail_info['refresh_job_id'])
                detail_info['window'].destroy()
            del self.open_detail_windows[server_key]


    def _update_detail_view(self, server_key, server_detail_data):
        """Updates the labels and player list in a specific detail window."""
        if server_key not in self.open_detail_windows or not self.open_detail_windows[server_key]['window'].winfo_exists():
            return

        detail_window_ref = self.open_detail_windows[server_key]['window']
        
        detail_labels_ref = detail_window_ref._detail_labels
        map_image_label_ref = detail_window_ref._map_image_label
        detail_player_tree_ref = detail_window_ref._detail_player_tree
        
        title_label_ref = detail_window_ref._title_label
        new_title_text = f"Details for {server_detail_data.get('display_hostname', 'N/A')}:{server_detail_data.get('port', 'N/A')}"
        title_label_ref.config(text=new_title_text)


        if not server_detail_data or server_detail_data['ping'].startswith('Error'):
            for label in detail_labels_ref.values():
                label.config(text="N/A", foreground=ERROR_COLOR)
            map_image_label_ref.config(image='')
            map_image_label_ref.image = None
            for item in detail_player_tree_ref.get_children():
                detail_player_tree_ref.delete(item)
            detail_player_tree_ref._player_color_images.clear()
            return

        detail_labels_ref['name'].config(text=f"Server Name: {server_detail_data.get('display_hostname', 'N/A')}", foreground=DARK_FG)
        detail_labels_ref['ip'].config(text=f"IP Address: {server_detail_data.get('original_ip', 'N/A')}:{server_detail_data.get('port', 'N/A')}", foreground=DARK_FG)
        ping_fg_color = ERROR_COLOR if server_detail_data.get('ping', '').startswith('Error') else DARK_FG
        detail_labels_ref['ping'].config(text=f"Ping: {server_detail_data.get('ping', 'N/A')}", foreground=ping_fg_color)
        
        detail_labels_ref['map'].config(text=f"Map: {server_detail_data.get('map', 'N/A')}", foreground=DARK_FG)
        detail_labels_ref['mode'].config(text=f"Game Mode: {server_detail_data.get('mode', 'N/A')}", foreground=DARK_FG)
        detail_labels_ref['players_count'].config(text=f"Players: {server_detail_data.get('players_count', 'N/A')}", foreground=DARK_FG)
        detail_labels_ref['spectators_count'].config(text=f"Spectators: {server_detail_data.get('spectators_count', 'N/A')}", foreground=DARK_FG)

        map_name = server_detail_data.get('map', '')
        map_image_path = os.path.join(os.getcwd(), "mapshots", f"{map_name}.jpg")

        if os.path.exists(map_image_path):
            try:
                img = Image.open(map_image_path)
                img.thumbnail((200, 150), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                map_image_label_ref.config(image=photo)
                map_image_label_ref.image = photo
            except Exception as e:
                print(f"Error loading map image {map_image_path}: {e}")
                map_image_label_ref.config(image='')
                map_image_label_ref.image = None
        else:
            map_image_label_ref.config(image='')
            map_image_label_ref.image = None

        for item in detail_player_tree_ref.get_children():
            detail_player_tree_ref.delete(item)
        detail_player_tree_ref._player_color_images.clear()
        
        self._insert_players_into_tree(detail_player_tree_ref, server_detail_data.get('players', []), simplified_columns=False)

    def _auto_refresh_details_handler(self, server_key):
        """Automatically refreshes the server details in a specific modal window."""
        if server_key not in self.open_detail_windows or not self.open_detail_windows[server_key]['window'].winfo_exists():
            return

        detail_window_ref = self.open_detail_windows[server_key]['window']
        
        actual_ip, port = server_key
        
        Thread(target=self._ping_and_update_detail_modal, args=(server_key, actual_ip, port)).start()
        
        refresh_job_id = detail_window_ref.after(5000, self._auto_refresh_details_handler, server_key)
        self.open_detail_windows[server_key]['refresh_job_id'] = refresh_job_id


    def _ping_and_update_detail_modal(self, server_key, actual_ip, port):
        """Pings a server and updates the detail modal with the new data."""
        err, response, ping_time = udp_command(actual_ip, port, 'status 31\0')
        
        current_server_data = {}
        initial_display_name = next((s_name for s_name, s_port, s_ip in self.servers if (s_ip, s_port) == server_key), "N/A")
        # If it's a favorite not in self.servers, get its name from favorite_servers_data
        if initial_display_name == "N/A" and server_key in self.favorite_servers_data:
             initial_display_name = self.favorite_servers_data[server_key].get('display_hostname', "N/A")


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
            self.server_data[server_key] = current_server_data
            if server_key in self.favorite_servers_data:
                 self.favorite_servers_data[server_key].update(current_server_data)

        self.root.after(0, self._update_detail_view, server_key, current_server_data)

    def _create_color_image(self, top_color_idx, bottom_color_idx):
        """Generates a PhotoImage with two vertical color blocks from Quake palette."""
        img_width, img_height_per_color = 20, 10
        total_height = img_height_per_color * 2

        top_rgb = QUAKE_COLOR_RGB_PALETTE.get(top_color_idx, (255, 0, 255))
        bottom_rgb = QUAKE_COLOR_RGB_PALETTE.get(bottom_color_idx, (0, 255, 255))

        img = Image.new('RGB', (img_width, total_height), 'black')
        draw = ImageDraw.Draw(img)

        draw.rectangle((0, 0, img_width, img_height_per_color), fill=top_rgb)
        draw.rectangle((0, img_height_per_color, img_width, total_height), fill=bottom_rgb)

        return ImageTk.PhotoImage(img)

    def _insert_players_into_tree(self, treeview, players_data, simplified_columns=False):
        """
        Helper method to insert players into a Treeview, separating players from spectators,
        sorting them, and applying a special tag to spectator rows.
        Also handles creating and embedding player color images.
        """
        actual_players = []
        spectators = []

        for p in players_data:
            if p.get('frags') == 'S':
                spectators.append(p)
            else:
                actual_players.append(p)
        
        actual_players.sort(key=lambda x: (-x.get('frags', 0) if isinstance(x.get('frags'), int) else 0, p.get('name', '').lower()))
        
        spectators.sort(key=lambda x: x.get('name', '').lower())

        for p in actual_players:
            top_color_idx = p.get('topcolor', 0)
            bottom_color_idx = p.get('bottomcolor', 0)
            color_image = self._create_color_image(top_color_idx, bottom_color_idx)
            treeview._player_color_images.append(color_image)

            treeview.insert('', 'end', 
                            values=(p.get('name', 'N/A'), p.get('frags', 'N/A'), p.get('time', 'N/A'), p.get('ping', 'N/A'), p.get('team', 'N/A')),
                            image=color_image,
                            tags=()
                           )
        
        for p in spectators:
            top_color_idx = p.get('topcolor', 0)
            bottom_color_idx = p.get('bottomcolor', 0)
            color_image = self._create_color_image(top_color_idx, bottom_color_idx)
            treeview._player_color_images.append(color_image)

            treeview.insert('', 'end', 
                            values=(p.get('name', 'N/A'), p.get('frags', 'N/A'), p.get('time', 'N/A'), p.get('ping', 'N/A'), p.get('team', 'N/A')),
                            image=color_image,
                            tags=('spectator_row',)
                           )


    def show_server_details(self, event):
        """Open a new window with detailed information about the selected server."""
        # Determine which tree is active and get selected item from it
        current_tab_id = self.notebook.select()
        if current_tab_id == self.all_servers_frame._w:
            tree_to_use = self.all_servers_tree
            items_map = self.all_servers_items
        elif current_tab_id == self.favorites_frame._w:
            tree_to_use = self.favorites_tree
            items_map = self.favorites_items
        else:
            return


        selected_item = tree_to_use.focus()
        if not selected_item:
            return

        found_key = None
        for key, item_id in items_map.items():
            if item_id == selected_item:
                found_key = key
                break

        if not found_key:
            messagebox.showerror("Error", "Could not find server details for the selected item.")
            return

        if found_key in self.open_detail_windows and self.open_detail_windows[found_key]['window'].winfo_exists():
            self.open_detail_windows[found_key]['window'].lift()
            return

        detail_window = tk.Toplevel(self.root)
        detail_window.geometry("600x400")
        detail_window.config(bg=DARK_BG)

        detail_window.overrideredirect(True)

        title_bar = ttk.Frame(detail_window, style='TFrame')
        title_bar.pack(fill='x')

        initial_display_hostname = self.server_data[found_key].get('display_hostname', 'N/A')
        port = self.server_data[found_key].get('port', 'N/A')
        title_label = ttk.Label(title_bar, text=f"Details for {initial_display_hostname}:{port}",
                                anchor='w', font=('TkDefaultFont', 10, 'bold'), 
                                background=BUTTON_BG, foreground=DARK_FG)
        title_label.pack(side='left', padx=5, pady=2, expand=True, fill='x')

        close_button = ttk.Button(title_bar, text='✕', command=lambda: self._on_detail_window_closing_handler(found_key),
                                  style='TButton', width=3)
        close_button.pack(side='right', padx=2, pady=2)

        detail_window._title_label = title_label

        title_bar.bind("<ButtonPress-1>", lambda event, dw=detail_window: self._start_drag_window(event, dw))
        title_bar.bind("<B1-Motion>", lambda event, dw=detail_window: self._drag_window(event, dw))
        title_label.bind("<ButtonPress-1>", lambda event, dw=detail_window: self._start_drag_window(event, dw))
        title_label.bind("<B1-Motion>", lambda event, dw=detail_window: self._drag_window(event, dw))

        detail_window._detail_labels = {}
        detail_window._map_image_label = ttk.Label(detail_window, background=DARK_BG)
        
        detail_window._detail_player_tree = ttk.Treeview(detail_window,
                                               columns=('Name', 'Frags', 'Time', 'Ping', 'Team'),
                                               show='headings',
                                               height=8,
                                               style='Treeview')
        detail_window._detail_player_tree._player_color_images = []
        
        detail_window._detail_player_tree.tag_configure('spectator_row', background=SPECTATOR_BG, foreground=DARK_FG)


        info_map_frame = ttk.Frame(detail_window, style='TFrame')
        info_map_frame.pack(padx=10, pady=5, fill='x')

        info_frame = ttk.Frame(info_map_frame, style='TFrame')
        info_frame.pack(side='left', fill='y', expand=False)

        label_keys = ['name', 'ip', 'ping', 'map', 'mode', 'players_count', 'spectators_count']
        for key in label_keys:
            label = ttk.Label(info_frame, text="", style='TLabel')
            label.pack(padx=0, pady=2, anchor='w')
            detail_window._detail_labels[key] = label

        detail_window._map_image_label.pack(side='right', padx=10, pady=5)

        detail_window._detail_player_tree.heading('Name', text='Name')
        detail_window._detail_player_tree.column('Name', width=160, anchor='w')
        detail_window._detail_player_tree.heading('Frags', text='Frags')
        detail_window._detail_player_tree.column('Frags', width=45)
        detail_window._detail_player_tree.heading('Time', text='Time')
        detail_window._detail_player_tree.column('Time', width=45)
        detail_window._detail_player_tree.heading('Ping', text='Ping')
        detail_window._detail_player_tree.column('Ping', width=45)
        detail_window._detail_player_tree.heading('Team', text='Team')
        detail_window._detail_player_tree.column('Team', width=80)
        
        detail_window._detail_player_tree.pack(padx=10, pady=5, fill='x')

        initial_server_data = self.server_data.get(found_key, {}) 
        self._update_detail_view(found_key, initial_server_data)
        
        actual_ip, port = found_key
        Thread(target=self._ping_and_update_detail_modal, args=(found_key, actual_ip, port)).start()
        
        refresh_job_id = detail_window.after(5000, self._auto_refresh_details_handler, found_key)
        
        self.open_detail_windows[found_key] = {
            'window': detail_window,
            'refresh_job_id': refresh_job_id
        }
        detail_window.protocol("WM_DELETE_WINDOW", lambda: self._on_detail_window_closing_handler(found_key))

    def _start_drag_window(self, event, window):
        window._offset_x = event.x
        window._offset_y = event.y

    def _drag_window(self, event, window):
        x = window.winfo_x() + event.x - window._offset_x
        y = window.winfo_y() + event.y - window._offset_y
        window.geometry(f"+{x}+{y}")


    def update_server_display(self, server_key, values_for_treeview):
        """Update the Treeview rows for a specific server in both active lists."""
        if self.root.winfo_exists() and not self.stop_event.is_set():
            with self.gui_lock:
                # Update in All Servers Tree
                item_id_all = self.all_servers_items.get(server_key)
                if item_id_all:
                    # Corrected: Use lambda to properly pass keyword arguments
                    self.root.after(0, lambda id=item_id_all, val=values_for_treeview: self.all_servers_tree.item(id, values=val))
                
                # Update in Favorites Tree
                item_id_fav = self.favorites_items.get(server_key)
                if item_id_fav:
                    # Corrected: Use lambda to properly pass keyword arguments
                    self.root.after(0, lambda id=item_id_fav, val=values_for_treeview: self.favorites_tree.item(id, values=val))
        else:
            print(f"Skipping GUI update for {server_key} as application is closing or GUI not found.")


def main():
    root = tk.Tk()
    root.geometry("700x400")
    app = QuakeWorldGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()