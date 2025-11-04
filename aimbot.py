import time
import json
import struct
import psutil
import ctypes
import win32gui
import win32con
import traceback
import win32process
import requests
import win32api
import math
import tkinter as tk
from tkinter import ttk
import keyboard
import threading
from ctypes import wintypes

root = tk.Tk()
root.withdraw()

OFFSETS_URL = "https://robloxoffsets.com/offsets.json"
try:
    resp = requests.get(OFFSETS_URL)
    OFFSETS = resp.json()
except Exception as e:
    print(f"Failed to fetch offsets: {e}")
    OFFSETS = {
        "FakeDataModelPointer": "0x0", "FakeDataModelToDataModel": "0x0", "Name": "0x0",
        "VisualEnginePointer": "0x0", "Children": "0x0", "ChildrenEnd": "0x0",
        "ClassDescriptor": "0x0", "ClassDescriptorToClassName": "0x0", "LocalPlayer": "0x0",
        "ModelInstance": "0x0", "Primitive": "0x0", "Position": "0x0", "PartSize": "0x0",
        "Health": "0x0", "MaxHealth": "0x0", "viewmatrix": "0x0", "PlaceId": "0x0", "Team": "0x0"
    }

class Settings:
    def __init__(self):
        self.aim_enabled = tk.BooleanVar(value=True)
        self.fov_radius = tk.DoubleVar(value=150.0)
        self.smoothness = tk.DoubleVar(value=5.0)
        self.aim_key = "ctrl"
        self.slippery_mode = tk.BooleanVar(value=False)
        self.blatant_mode = tk.BooleanVar(value=False)
        self.target_part = tk.StringVar(value="Head")
        self.prediction_enabled = tk.BooleanVar(value=True)
        self.prediction_time = tk.DoubleVar(value=0.1)

settings = Settings()

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32Usage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(wintypes.DWORD)),
        ("th32ModuleID", wintypes.DWORD),
        ("th32Threads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260)
    ]

class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(wintypes.BYTE)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", ctypes.c_char * 256),
        ("szExePath", ctypes.c_char * 260)
    ]

class vec2:
    def __init__(self, x=0.0, y=0.0):
        self.x = x
        self.y = y

class vec3:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x = x
        self.y = y
        self.z = z

class robloxmemory:
    def __init__(self):
        if not self.find_roblox_process():
            raise Exception("failed to find roblox process.")
        self.initialize_game_data()

    def find_roblox_process(self):
        hwnd, pid = self.find_window_by_exe("RobloxPlayerBeta.exe")
        if pid:
            self.hwnd = hwnd
            self.process_id = pid
        else:
            pid = self.get_process_id_by_psutil("RobloxPlayerBeta.exe")
            if not pid:
                return False
            self.process_id = pid
            hwnd, _ = self.find_window_by_exe("RobloxPlayerBeta.exe")
            self.hwnd = hwnd if hwnd else None
        self.process_handle = ctypes.windll.kernel32.OpenProcess(win32con.PROCESS_ALL_ACCESS, False, self.process_id)
        if not self.process_handle:
            return False
        self.base_address = self.get_module_address("RobloxPlayerBeta.exe")
        if not self.base_address:
            ctypes.windll.kernel32.CloseHandle(self.process_handle)
            return False
        return True

    def find_window_by_exe(self, exe_name):
        matches = []
        def enum_proc(hwnd, _):
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    p = psutil.Process(pid)
                    pname = (p.name() or "").lower()
                    target = exe_name.lower()
                    target_noexe = target[:-4] if target.endswith(".exe") else target
                    if pname == target or pname == target_noexe:
                        matches.append((hwnd, pid))
                except Exception:
                    pass
                return True
            except Exception:
                return True
        try:
            win32gui.EnumWindows(enum_proc, None)
        except Exception:
            pass
        if matches:
            for hwnd, pid in matches:
                title = win32gui.GetWindowText(hwnd)
                if title:
                    return hwnd, pid
            return matches[0]
        return None, None

    def get_process_id_by_psutil(self, process_name):
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'].lower() == process_name.lower():
                        return proc.info['pid']
                except Exception:
                    continue
            return None
        except Exception:
            return None

    def get_module_address(self, module_name):
        if not getattr(self, 'process_handle', None):
            return None
        snapshot = ctypes.windll.kernel32.CreateToolhelp32Snapshot(0x8 | 0x10, self.process_id)
        if snapshot == -1:
            return None
        module_entry = MODULEENTRY32()
        module_entry.dwSize = ctypes.sizeof(MODULEENTRY32)
        if ctypes.windll.kernel32.Module32First(snapshot, ctypes.byref(module_entry)):
            while True:
                try:
                    name = module_entry.szModule.decode().lower()
                except Exception:
                    name = ""
                if module_name.lower() == name:
                    ctypes.windll.kernel32.CloseHandle(snapshot)
                    return ctypes.addressof(module_entry.modBaseAddr.contents)
                if not ctypes.windll.kernel32.Module32Next(snapshot, ctypes.byref(module_entry)):
                    break
        ctypes.windll.kernel32.CloseHandle(snapshot)
        return None

    def read_memory(self, address, size):
        buffer = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t()
        result = ctypes.windll.kernel32.ReadProcessMemory(self.process_handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(bytes_read))
        if result and bytes_read.value > 0:
            return buffer.raw[:bytes_read.value]
        return None

    def read_ptr(self, address):
        data = self.read_memory(address, 8)
        if data:
            return int.from_bytes(data, byteorder='little')
        return None

    def read_int(self, address):
        data = self.read_memory(address, 4)
        if data:
            return int.from_bytes(data, byteorder='little', signed=True)
        return None

    def read_int64(self, address):
        data = self.read_memory(address, 8)
        if data:
            return struct.unpack('q', data)[0]
        return None

    def read_float(self, address):
        data = self.read_memory(address, 4)
        if data:
            return struct.unpack('f', data)[0]
        return None

    def read_string(self, address):
        if not address:
            return ""
        str_length = self.read_int(address + 0x18)
        if not str_length or str_length <= 0 or str_length > 1000:
            return ""
        if str_length >= 16:
            address = self.read_ptr(address)
            if not address:
                return ""
        result = ""
        offset = 0
        while offset < str_length:
            char_data = self.read_memory(address + offset, 1)
            if not char_data:
                break
            char_val = char_data[0]
            if char_val == 0:
                break
            result += chr(char_val)
            offset += 1
        return result

    def initialize_game_data(self):
        try:
            fake_data_model = self.read_ptr(self.base_address + int(OFFSETS["FakeDataModelPointer"], 16))
            if not fake_data_model or fake_data_model == 0xFFFFFFFF:
                return
            data_model_pointer = self.read_ptr(fake_data_model + int(OFFSETS["FakeDataModelToDataModel"], 16))
            if not data_model_pointer or data_model_pointer == 0xFFFFFFFF:
                return
            retry_count = 0
            data_model_name = ""
            while retry_count < 30:
                name_ptr = self.read_ptr(data_model_pointer + int(OFFSETS["Name"], 16)) if data_model_pointer else None
                data_model_name = self.read_string(name_ptr) if name_ptr else ""
                if data_model_name == "Ugc":
                    break
                time.sleep(1)
                retry_count += 1
                fake_data_model = self.read_ptr(self.base_address + int(OFFSETS["FakeDataModelPointer"], 16))
                if fake_data_model:
                    data_model_pointer = self.read_ptr(fake_data_model + int(OFFSETS["FakeDataModelToDataModel"], 16))
            if data_model_name != "Ugc":
                return
            self.data_model = data_model_pointer
            self.visual_engine = self.read_ptr(self.base_address + int(OFFSETS["VisualEnginePointer"], 16))
            if not self.visual_engine or self.visual_engine == 0xFFFFFFFF:
                self.visual_engine = None
                return
            self.workspace = self.find_first_child_which_is_a(self.data_model, "Workspace") if self.data_model else None
            self.players = self.find_first_child_which_is_a(self.data_model, "Players") if self.data_model else None
            if self.workspace:
                self.camera = self.find_first_child_which_is_a(self.workspace, "Camera")
            else:
                self.camera = None
            if self.players:
                local_player_ptr = self.read_ptr(self.players + int(OFFSETS["LocalPlayer"], 16)) if self.players else None
                if local_player_ptr:
                    self.local_player = local_player_ptr
                else:
                    self.local_player = None
            else:
                self.local_player = None
        except Exception:
            pass

    def get_children(self, parent_address):
        children = []
        if not parent_address:
            return children
        children_ptr = self.read_ptr(parent_address + int(OFFSETS["Children"], 16))
        if not children_ptr:
            return children
        children_end = self.read_ptr(children_ptr + int(OFFSETS["ChildrenEnd"], 16))
        current_child = self.read_ptr(children_ptr)
        while current_child < children_end:
            child_ptr = self.read_ptr(current_child)
            if child_ptr:
                children.append(child_ptr)
            current_child += 0x10
        return children

    def get_instance_name(self, address):
        if not address:
            return ""
        name_ptr = self.read_ptr(address + int(OFFSETS["Name"], 16))
        return self.read_string(name_ptr) if name_ptr else ""

    def get_instance_class(self, address):
        if not address:
            return ""
        class_descriptor = self.read_ptr(address + int(OFFSETS["ClassDescriptor"], 16))
        if class_descriptor:
            class_name_ptr = self.read_ptr(class_descriptor + int(OFFSETS["ClassDescriptorToClassName"], 16))
            return self.read_string(class_name_ptr) if class_name_ptr else ""
        return ""

    def find_first_child_which_is_a(self, parent_address, class_name):
        children = self.get_children(parent_address)
        for child in children:
            if self.get_instance_class(child) == class_name:
                return child
        return None

    def find_first_child_by_name(self, parent_address, name):
        children = self.get_children(parent_address)
        for child in children:
            if self.get_instance_name(child) == name:
                return child
        return None

    def read_matrix4(self, address):
        data = self.read_memory(address, 64)
        if data:
            matrix = []
            for i in range(16):
                matrix.append(struct.unpack('f', data[i*4:(i+1)*4])[0])
            return matrix
        return None

    def get_team(self, player_ptr):
        if not player_ptr:
            return None
        team_ptr = self.read_ptr(player_ptr + int(OFFSETS.get("Team", "0x0"), 16))
        if not team_ptr:
            return None
        return team_ptr

    def get_player_coordinates(self):
        if not getattr(self, 'players', None) or not getattr(self, 'local_player', None):
            return []
        coordinates = []
        player_instances = self.get_children(self.players)
        for player_ptr in player_instances:
            if not player_ptr:
                continue
            if player_ptr == self.local_player:
                continue
            player_name = self.get_instance_name(player_ptr)
            if not player_name:
                continue
            character_ptr = self.read_ptr(player_ptr + int(OFFSETS["ModelInstance"], 16))
            if not character_ptr:
                continue
            if self.get_instance_class(character_ptr) != "Model":
                continue
            humanoid_root_part = self.find_first_child_by_name(character_ptr, "HumanoidRootPart")
            if not humanoid_root_part:
                continue
            if self.get_instance_class(humanoid_root_part) != "Part":
                continue
            primitive = self.read_ptr(humanoid_root_part + int(OFFSETS["Primitive"], 16))
            if not primitive:
                continue
            position_data = self.read_memory(primitive + int(OFFSETS["Position"], 16), 12)
            if not position_data:
                continue
            x, y, z = struct.unpack('fff', position_data)
            position = vec3(x, y, z)
            size_data = self.read_memory(primitive + int(OFFSETS["PartSize"], 16), 12)
            if size_data:
                sx, sy, sz = struct.unpack('fff', size_data)
                player_size = vec3(sx, sy, sz)
            else:
                player_size = vec3(2.0, 5.0, 1.0)
            head_part = self.find_first_child_by_name(character_ptr, "Head")
            head_pos = None
            if head_part:
                head_primitive = self.read_ptr(head_part + int(OFFSETS["Primitive"], 16))
                if head_primitive:
                    head_position_data = self.read_memory(head_primitive + int(OFFSETS["Position"], 16), 12)
                    if head_position_data:
                        hx, hy, hz = struct.unpack('fff', head_position_data)
                        head_pos = vec3(hx, hy, hz)
            if not head_pos:
                head_pos = vec3(position.x, position.y + player_size.y / 2 + 1.0, position.z)
            
            torso_part = self.find_first_child_by_name(character_ptr, "Torso")
            torso_pos = None
            if torso_part:
                torso_primitive = self.read_ptr(torso_part + int(OFFSETS["Primitive"], 16))
                if torso_primitive:
                    torso_position_data = self.read_memory(torso_primitive + int(OFFSETS["Position"], 16), 12)
                    if torso_position_data:
                        tx, ty, tz = struct.unpack('fff', torso_position_data)
                        torso_pos = vec3(tx, ty, tz)
            if not torso_pos:
                torso_pos = position
            
            humanoid = self.find_first_child_which_is_a(character_ptr, "Humanoid")
            health = None
            max_health = None
            if humanoid:
                health_addr = humanoid + int(OFFSETS["Health"], 16)
                max_health_addr = humanoid + int(OFFSETS["MaxHealth"], 16)
                health = self.read_float(health_addr)
                max_health = self.read_float(max_health_addr)
            
            coordinates.append({
                "player_name": player_name,
                "root_pos": position,
                "head_pos": head_pos,
                "torso_pos": torso_pos,
                "player_size": player_size,
                "player_ptr": player_ptr,
                "character_ptr": character_ptr,
                "humanoid_root_part_ptr": humanoid_root_part,
                "health": health,
                "max_health": max_health
            })
        return coordinates

    def get_window_viewport(self):
        if not getattr(self, 'hwnd', None):
            return vec2(1920, 1080)
        try:
            left, top, right, bottom = win32gui.GetClientRect(self.hwnd)
            width = float(right - left)
            height = float(bottom - top)
            if width <= 0 or height <= 0:
                rect = win32gui.GetWindowRect(self.hwnd)
                width = float(rect[2] - rect[0])
                height = float(rect[3] - rect[1])
            return vec2(width, height)
        except Exception:
            return vec2(1920, 1080)

    def world_to_screen(self, pos):
        if not getattr(self, 'visual_engine', None):
            return vec2(-1, -1)
        try:
            view_matrix = self.read_matrix4(self.visual_engine + int(OFFSETS["viewmatrix"], 16))
            if not view_matrix:
                return vec2(-1, -1)
            qx = (pos.x * view_matrix[0]) + (pos.y * view_matrix[1]) + (pos.z * view_matrix[2]) + view_matrix[3]
            qy = (pos.x * view_matrix[4]) + (pos.y * view_matrix[5]) + (pos.z * view_matrix[6]) + view_matrix[7]
            qz = (pos.x * view_matrix[8]) + (pos.y * view_matrix[9]) + (pos.z * view_matrix[10]) + view_matrix[11]
            qw = (pos.x * view_matrix[12]) + (pos.y * view_matrix[13]) + (pos.z * view_matrix[14]) + view_matrix[15]
            if qw < 0.1:
                return vec2(-1, -1)
            ndc_x = qx / qw
            ndc_y = qy / qw
            viewport = self.get_window_viewport()
            width = viewport.x
            height = viewport.y
            x = (width / 2.0) * (1.0 + ndc_x)
            y = (height / 2.0) * (1.0 - ndc_y)
            if x < 0 or x > width or y < 0 or y > height:
                return vec2(-1, -1)
            return vec2(x, y)
        except Exception:
            return vec2(-1, -1)

    def get_place_id(self):
        if not getattr(self, 'data_model', None):
            return None
        try:
            place_id = self.read_int64(self.data_model + int(OFFSETS["PlaceId"], 16))
            return place_id if place_id else None
        except Exception:
            return None

    def print_game_info(self):
        player_coords = self.get_player_coordinates()
        print(f"found {len(player_coords)} player instances [humanoids]")
        for p in player_coords:
            root_pos = p["root_pos"]
            health_info = f"health: {p['health']:.1f}/{p['max_health']:.1f}" if p['health'] is not None and p['max_health'] is not None else "health: Unknown"
            print(f"got pos : {p['player_name']}: ({root_pos.x:.2f}, {root_pos.y:.2f}, {root_pos.z:.2f}) | {health_info}")

def create_menu():
    menu_root = tk.Toplevel()
    menu_root.title("Aimbot | ROBLOX")
    menu_root.geometry("400x500")
    menu_root.attributes("-topmost", True)

    tk.Label(menu_root, text="=== AIM ===", font=("Arial", 9, "bold")).pack(pady=5)
    tk.Checkbutton(menu_root, text="Enable Aim", variable=settings.aim_enabled).pack(pady=2)
    tk.Checkbutton(menu_root, text="Slippery Mode (Lock)", variable=settings.slippery_mode).pack(pady=2)
    tk.Checkbutton(menu_root, text="Blatant Mode (No Smooth)", variable=settings.blatant_mode).pack(pady=2)
    
    target_frame = tk.Frame(menu_root)
    tk.Label(target_frame, text="Target Part:").pack(side=tk.LEFT)
    target_combo = tk.ttk.Combobox(target_frame, textvariable=settings.target_part, 
                                    values=["Head", "Torso", "HumanoidRootPart"], 
                                    state="readonly", width=15)
    target_combo.pack(side=tk.LEFT, padx=5)
    target_frame.pack(pady=5)
    
    tk.Checkbutton(menu_root, text="Enable Prediction", variable=settings.prediction_enabled).pack(pady=2)
    
    prediction_frame = tk.Frame(menu_root)
    tk.Label(prediction_frame, text="Prediction Time:").pack(side=tk.LEFT)
    tk.Scale(prediction_frame, from_=0.0, to=0.5, resolution=0.01, orient=tk.HORIZONTAL, 
             variable=settings.prediction_time).pack(side=tk.LEFT, fill=tk.X, expand=True)
    prediction_frame.pack(fill=tk.X, padx=10, pady=5)

    fov_frame = tk.Frame(menu_root)
    tk.Label(fov_frame, text="FOV Radius:").pack(side=tk.LEFT)
    tk.Scale(fov_frame, from_=10, to=500, orient=tk.HORIZONTAL, variable=settings.fov_radius).pack(side=tk.LEFT, fill=tk.X, expand=True)
    fov_frame.pack(fill=tk.X, padx=10, pady=5)

    smooth_frame = tk.Frame(menu_root)
    tk.Label(smooth_frame, text="Smoothness:").pack(side=tk.LEFT)
    tk.Scale(smooth_frame, from_=1, to=20, orient=tk.HORIZONTAL, variable=settings.smoothness).pack(side=tk.LEFT, fill=tk.X, expand=True)
    smooth_frame.pack(fill=tk.X, padx=10, pady=5)

    key_frame = tk.Frame(menu_root)
    tk.Label(key_frame, text="Aim Key:").pack(side=tk.LEFT)
    initial_key_text = settings.aim_key.upper()
    if settings.aim_key == 'x1':
        initial_key_text = 'MB4/X1'
    elif settings.aim_key == 'x2':
        initial_key_text = 'MB5/X2'
    elif settings.aim_key == 'left':
        initial_key_text = 'LMB'
    elif settings.aim_key == 'right':
        initial_key_text = 'RMB'
    elif settings.aim_key == 'middle':
        initial_key_text = 'MMB'
    key_button = tk.Button(key_frame, text=initial_key_text, width=12, relief=tk.SUNKEN)
    key_status_label = tk.Label(key_frame, text="", fg="green", font=("Arial", 8))
    key_hook = None
    mouse_hook = None
    capture_active = False
    mouse_check_thread = None
    
    def finish_capture(key_name, display_name):
        nonlocal key_hook, mouse_hook, capture_active, mouse_check_thread
        capture_active = False
        if key_hook is not None:
            try:
                keyboard.unhook(key_hook)
            except:
                pass
            key_hook = None
        if mouse_hook is not None:
            try:
                keyboard.unhook(mouse_hook)
            except:
                pass
            mouse_hook = None
        
        settings.aim_key = key_name
        key_button.config(text=display_name, relief=tk.SUNKEN, bg="SystemButtonFace")
        key_status_label.config(text="✓ Set!", fg="green")
        key_status_label.after(2000, lambda: key_status_label.config(text=""))
    
    def start_key_bind():
        nonlocal key_hook, mouse_hook, capture_active, mouse_check_thread
        if capture_active:
            return
        
        if key_hook is not None:
            try:
                keyboard.unhook(key_hook)
            except:
                pass
        if mouse_hook is not None:
            try:
                keyboard.unhook(mouse_hook)
            except:
                pass
        
        capture_active = True
        key_hook = None
        mouse_hook = None
        
        key_button.config(text="Нажмите...", relief=tk.RAISED, bg="yellow")
        key_status_label.config(text="", fg="green")
        
        def check_mouse_buttons():
            VK_XBUTTON1 = 0x05
            VK_XBUTTON2 = 0x06
            VK_LBUTTON = 0x01
            VK_RBUTTON = 0x02
            VK_MBUTTON = 0x04
            
            last_states = {
                VK_XBUTTON1: False,
                VK_XBUTTON2: False,
                VK_LBUTTON: False,
                VK_RBUTTON: False,
                VK_MBUTTON: False,
            }
            
            while capture_active:
                try:
                    state1 = win32api.GetAsyncKeyState(VK_XBUTTON1) & 0x8000
                    state2 = win32api.GetAsyncKeyState(VK_XBUTTON2) & 0x8000
                    state_l = win32api.GetAsyncKeyState(VK_LBUTTON) & 0x8000
                    state_r = win32api.GetAsyncKeyState(VK_RBUTTON) & 0x8000
                    state_m = win32api.GetAsyncKeyState(VK_MBUTTON) & 0x8000
                    
                    if state1 and not last_states[VK_XBUTTON1]:
                        finish_capture('x1', 'MB4/X1')
                        break
                    elif state2 and not last_states[VK_XBUTTON2]:
                        finish_capture('x2', 'MB5/X2')
                        break
                    elif state_l and not last_states[VK_LBUTTON]:
                        finish_capture('left', 'LMB')
                        break
                    elif state_r and not last_states[VK_RBUTTON]:
                        finish_capture('right', 'RMB')
                        break
                    elif state_m and not last_states[VK_MBUTTON]:
                        finish_capture('middle', 'MMB')
                        break
                    
                    last_states[VK_XBUTTON1] = bool(state1)
                    last_states[VK_XBUTTON2] = bool(state2)
                    last_states[VK_LBUTTON] = bool(state_l)
                    last_states[VK_RBUTTON] = bool(state_r)
                    last_states[VK_MBUTTON] = bool(state_m)
                    
                    time.sleep(0.01)
                except Exception:
                    break
        
        mouse_check_thread = threading.Thread(target=check_mouse_buttons, daemon=True)
        mouse_check_thread.start()
        
        def on_key_press(event):
            if not capture_active:
                return
            
            try:
                key_name = event.name.lower()
                if 'mouse' in key_name or key_name in ['x1', 'x2', 'left', 'right', 'middle']:
                    return
                
                finish_capture(key_name, key_name.upper())
            except Exception:
                pass
        
        key_hook = keyboard.on_press(on_key_press, suppress=False)
    
    key_button.config(command=start_key_bind)
    key_button.pack(side=tk.LEFT, padx=5)
    key_status_label.pack(side=tk.LEFT)
    key_frame.pack(pady=10)

def main_loop():
    try:
        external = robloxmemory()
        print("Roblox external found. Starting aimlock loop...")
    except Exception as e:
        print(f"err : {e}")
        traceback.print_exc()
        return

    fov_canvas = None
    root_fov = None
    current_target_ptr = None
    current_fov_radius = 150.0
    target_fov_radius = 150.0

    def create_fov_circle():
        nonlocal root_fov, fov_canvas, current_fov_radius, target_fov_radius
        try:
            root_fov = tk.Toplevel()
            root_fov.geometry("300x300+100+100")
            root_fov.attributes("-transparentcolor", "black", "-topmost", True, "-alpha", 0.5)
            root_fov.overrideredirect(True)
            fov_canvas = tk.Canvas(root_fov, bg="black", highlightthickness=0)
            fov_canvas.pack(fill=tk.BOTH, expand=True)
            current_fov_radius = settings.fov_radius.get()
            target_fov_radius = current_fov_radius
            update_fov_circle()
        except Exception:
            root.after(100, create_fov_circle)

    def update_fov_circle():
        nonlocal current_fov_radius, target_fov_radius
        if not fov_canvas:
            return
        fov_canvas.delete("all")
        
        target_fov_radius = settings.fov_radius.get()
        diff = target_fov_radius - current_fov_radius
        if abs(diff) > 0.5:
            current_fov_radius += diff * 0.15
        else:
            current_fov_radius = target_fov_radius
        
        radius = current_fov_radius
        viewport = external.get_window_viewport()
        center_x = viewport.x / 2.0
        center_y = viewport.y / 2.0
        
        try:
            win_x = root_fov.winfo_x()
            win_y = root_fov.winfo_y()
            win_width = root_fov.winfo_width()
            win_height = root_fov.winfo_height()

            new_width = int(radius * 2 + 2)
            new_height = int(radius * 2 + 2)
            new_x = int(center_x - radius)
            new_y = int(center_y - radius)

            if abs(win_width - new_width) > 1 or abs(win_height - new_height) > 1:
                width_diff = new_width - win_width
                height_diff = new_height - win_height
                x_diff = new_x - win_x
                y_diff = new_y - win_y
                
                smooth_width = int(win_width + width_diff * 0.15)
                smooth_height = int(win_height + height_diff * 0.15)
                smooth_x = int(win_x + x_diff * 0.15)
                smooth_y = int(win_y + y_diff * 0.15)
                
                root_fov.geometry(f"{smooth_width}x{smooth_height}+{smooth_x}+{smooth_y}")

            fov_canvas.create_oval(1, 1, radius * 2, radius * 2, outline="red", width=1)
        except Exception:
            pass
        
        root_fov.after(16, update_fov_circle)

    root.after(100, create_fov_circle)

    player_positions_history = {}
    
    def get_target_part_pos(player):
        target_part_name = settings.target_part.get()
        if target_part_name == "Head":
            return player.get("head_pos")
        elif target_part_name == "Torso":
            return player.get("torso_pos")
        elif target_part_name == "HumanoidRootPart":
            return player.get("root_pos")
        return player.get("head_pos")
    
    def predict_position(current_pos, player_ptr, prediction_time):
        if not settings.prediction_enabled.get() or prediction_time <= 0:
            return current_pos
        
        if player_ptr not in player_positions_history:
            player_positions_history[player_ptr] = []
        
        history = player_positions_history[player_ptr]
        history.append((time.time(), current_pos))
        
        if len(history) > 10:
            history.pop(0)
        
        if len(history) < 2:
            return current_pos
        
        dt = history[-1][0] - history[-2][0]
        if dt <= 0:
            return current_pos
        
        prev_pos = history[-2][1]
        curr_pos = history[-1][1]
        
        velocity = vec3(
            (curr_pos.x - prev_pos.x) / dt,
            (curr_pos.y - prev_pos.y) / dt,
            (curr_pos.z - prev_pos.z) / dt
        )
        
        predicted = vec3(
            curr_pos.x + velocity.x * prediction_time,
            curr_pos.y + velocity.y * prediction_time,
            curr_pos.z + velocity.z * prediction_time
        )
        
        return predicted

    def is_key_pressed(key_name):
        if key_name in ['x1', 'x2', 'left', 'right', 'middle']:
            VK_XBUTTON1 = 0x05
            VK_XBUTTON2 = 0x06
            VK_LBUTTON = 0x01
            VK_RBUTTON = 0x02
            VK_MBUTTON = 0x04
            
            key_map = {
                'x1': VK_XBUTTON1,
                'x2': VK_XBUTTON2,
                'left': VK_LBUTTON,
                'right': VK_RBUTTON,
                'middle': VK_MBUTTON,
            }
            
            vk_code = key_map.get(key_name)
            if vk_code:
                return bool(win32api.GetAsyncKeyState(vk_code) & 0x8000)
            return False
        else:
            try:
                return keyboard.is_pressed(key_name)
            except:
                return False

    while True:
        try:
            if is_key_pressed(settings.aim_key) and settings.aim_enabled.get():
                player_coords = external.get_player_coordinates()
                if not player_coords:
                    time.sleep(0.01)
                    continue

                viewport = external.get_window_viewport()
                screen_center_x = viewport.x / 2.0
                screen_center_y = viewport.y / 2.0
                
                fov = settings.fov_radius.get()
                min_dist = float('inf')
                target_pos = None
                found_target_this_frame = False
                prediction_time = settings.prediction_time.get()

                if settings.slippery_mode.get() and current_target_ptr is not None:
                    for p in player_coords:
                        if p["player_ptr"] == current_target_ptr:
                            if p['health'] is not None and p['health'] > 0:
                                target_part_pos = get_target_part_pos(p)
                                predicted_pos = predict_position(target_part_pos, p["player_ptr"], prediction_time)
                                target_screen_pos = external.world_to_screen(predicted_pos)
                                if target_screen_pos.x != -1 and target_screen_pos.y != -1:
                                    target_pos = target_screen_pos
                                    found_target_this_frame = True
                            else:
                                current_target_ptr = None
                                if p["player_ptr"] in player_positions_history:
                                    del player_positions_history[p["player_ptr"]]
                            break
                    if not found_target_this_frame:
                         current_target_ptr = None

                if not found_target_this_frame:
                    for p in player_coords:
                        if p['health'] is not None and p['health'] <= 0:
                            continue
                        
                        target_part_pos = get_target_part_pos(p)
                        predicted_pos = predict_position(target_part_pos, p["player_ptr"], prediction_time)
                        target_screen_pos = external.world_to_screen(predicted_pos)
                        if target_screen_pos.x != -1 and target_screen_pos.y != -1:
                            dist = math.sqrt((target_screen_pos.x - screen_center_x)**2 + (target_screen_pos.y - screen_center_y)**2)
                            
                            if dist < min_dist and dist <= fov:
                                min_dist = dist
                                target_pos = target_screen_pos
                                current_target_ptr = p["player_ptr"]
                
                if target_pos:
                    delta_x = target_pos.x - screen_center_x
                    delta_y = target_pos.y - screen_center_y
                    
                    if settings.blatant_mode.get():
                        move_x = int(delta_x)
                        move_y = int(delta_y)
                    else:
                        smooth = settings.smoothness.get()
                        if smooth <= 0:
                            smooth = 1.0
                        
                        move_x = int(delta_x / smooth)
                        move_y = int(delta_y / smooth)
                        
                        if abs(move_x) < 1 and abs(delta_x) > 0:
                            move_x = 1 if delta_x > 0 else -1
                        if abs(move_y) < 1 and abs(delta_y) > 0:
                            move_y = 1 if delta_y > 0 else -1

                    win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, move_x, move_y, 0, 0)
            else:
                current_target_ptr = None
                player_positions_history.clear()

            time.sleep(0.001)

        except Exception as e:
            print(f"Loop error: {e}")
            traceback.print_exc()
            try:
                external = robloxmemory()
                print("Re-initialized robloxmemory after error.")
            except Exception as re_e:
                print(f"Failed to re-initialize: {re_e}")
                time.sleep(1)

if __name__ == "__main__":
    threading.Thread(target=main_loop, daemon=True).start()
    create_menu()
    root.mainloop()