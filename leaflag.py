import subprocess as sp
import ctypes as ct
import atexit
import keyboard
import psutil
import threading
import sys
import time
from typing import Optional

# ---- PyInstaller --noconsole safety (prevents sys.stdout/sys.stderr None issues) ----
class _NullWriter:
    def write(self, _): pass
    def flush(self): pass

if sys.stdout is None:
    sys.stdout = _NullWriter()
if sys.stderr is None:
    sys.stderr = _NullWriter()

import customtkinter as ctk
from win32gui import GetForegroundWindow, GetWindowRect, SetWindowPos
import win32con as wc
import win32process

RULE_NAME = "Roblox_Block"
DEFAULT_KEYBIND = "f6"


class LeafLag:
    def __init__(self) -> None:
        self.settings = {
            'Keybind': DEFAULT_KEYBIND,
            'Lagswitch': 'off',
            'AutoTurnOff': False,      # Anti-Timeout
            'AutoTurnBackOn': False,   # Reactivate
            'Overlay': False
        }

        self.block_flag = False
        self.lagswitch_active = False
        self.timer_duration = 9.8
        self.reactivation_duration = 0.2

        self.lagswitch_cycle_event = threading.Event()

        # Anti-timeout countdown state
        self.countdown_label: Optional[ctk.CTkLabel] = None
        self.countdown_job: Optional[str] = None
        self.countdown_end_time: float = 0.0

        self.status_window = None
        self.overlay_update_event = threading.Event()

        ctk.set_appearance_mode('dark')
        ctk.set_default_color_theme('blue')

        # Requirements 
        self.check_requirements()

        self.root = ctk.CTk()
        self.root.title('Leaf Lag V2.3.2')
        self.root.geometry('370x210')
        self.root.resizable(False, False)
        self.root.attributes('-topmost', True)

        self.setup_ui()
        self.setup_keybind()

    # ---------------- Requirements / Messages ----------------

    def show_message(self, message: str) -> None:
        try:
            ct.windll.user32.MessageBoxW(0, message, 'Leaf Lag V2.3.2', 0)
        except Exception:
            pass

    def is_admin(self) -> bool:
        try:
            return bool(ct.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def is_roblox_running(self) -> bool:
        try:
            for proc in psutil.process_iter(['name']):
                name = (proc.info.get('name') or '').lower()
                if name == 'robloxplayerbeta.exe':
                    return True
        except Exception:
            pass
        return False

    def check_requirements(self) -> None:
        if not self.is_admin():
            self.show_message('Leaf LagSwitch requires administrator privileges to run.')
            sys.exit(1)

        if not self.is_roblox_running():
            self.show_message('Roblox is not running. Please start Roblox and try again.')
            sys.exit(1)

    # ---------------- UI ----------------

    def setup_ui(self) -> None:
        self.status_label = ctk.CTkLabel(
            self.root,
            text='LagSwitch off.',
            text_color='red',
            font=('TkDefaultFont', 15, 'bold')
        )
        self.status_label.grid(row=0, column=0, padx=10, pady=0)

        ctk.CTkLabel(
            self.root,
            text='Made By SquareszLeaf, Forked By Barztu',
            wraplength=160,
            justify="left"
        ).grid(row=0, column=1, padx=10, pady=0, sticky="w")

        self.keybind_label = ctk.CTkLabel(
            self.root, text=f"Keybind: {self.settings['Keybind']}"
        )
        self.keybind_label.grid(row=1, column=0, padx=10, pady=4)

        ctk.CTkButton(
            self.root,
            text='Change Keybind',
            command=self.change_keybind
        ).grid(row=2, column=0, padx=10, pady=4)

        self.auto_turnoff_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self.root,
            text='Anti-Timeout',
            variable=self.auto_turnoff_var,
            command=self.update_auto_turnoff
        ).grid(row=3, column=0, padx=10, pady=4)

        self.auto_turnbackon_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self.root,
            text='Reactivate',
            variable=self.auto_turnbackon_var,
            command=self.update_auto_turnbackon
        ).grid(row=4, column=0, padx=10, pady=4)

        self.timer_slider = ctk.CTkSlider(
            self.root,
            from_=0,
            to=10,
            number_of_steps=100,
            command=self.update_timer_duration
        )
        self.timer_slider.set(self.timer_duration)
        self.timer_slider.grid(row=3, column=1, padx=10, pady=4)

        self.timer_label = ctk.CTkLabel(
            self.root,
            text=f"{self.timer_duration:.1f}s"
        )
        self.timer_label.grid(row=3, column=1, padx=10, pady=4)

        self.reactivation_slider = ctk.CTkSlider(
            self.root,
            from_=0,
            to=1,
            number_of_steps=10,
            command=self.update_reactivation_duration
        )
        self.reactivation_slider.set(self.reactivation_duration)
        self.reactivation_slider.grid(row=4, column=1, padx=10, pady=4)

        self.reactivation_label = ctk.CTkLabel(
            self.root,
            text=f"{self.reactivation_duration:.1f}s"
        )
        self.reactivation_label.grid(row=4, column=1, padx=10, pady=4)

        # Anti-timeout countdown label
        self.countdown_label = ctk.CTkLabel(
            self.root,
            text="Anti-Timeout: --.-s",
            font=('TkDefaultFont', 13, 'bold')
        )
        self.countdown_label.grid(
            row=5, column=0, columnspan=2, padx=10, pady=(4, 6), sticky="w"
        )

    # ---------------- Countdown ----------------

    def start_anti_timeout_countdown(self) -> None:
        if not self.settings['AutoTurnOff'] or not self.lagswitch_active or not self.block_flag:
            self.stop_anti_timeout_countdown()
            return

        self.countdown_end_time = time.time() + self.timer_duration
        self._countdown_tick()

    def stop_anti_timeout_countdown(self) -> None:
        if self.countdown_job:
            try:
                self.root.after_cancel(self.countdown_job)
            except Exception:
                pass
            self.countdown_job = None

        if self.countdown_label:
            self.countdown_label.configure(text="Anti-Timeout: --.-s")

    def _countdown_tick(self) -> None:
        if not self.settings['AutoTurnOff'] or not self.lagswitch_active or not self.block_flag:
            self.stop_anti_timeout_countdown()
            return

        remaining = max(0.0, self.countdown_end_time - time.time())
        if self.countdown_label:
            self.countdown_label.configure(text=f"Anti-Timeout: {remaining:.1f}s")

        if remaining > 0:
            self.countdown_job = self.root.after(100, self._countdown_tick)

    # ---------------- Logic ----------------

    def activate_lagswitch(self) -> None:
        # If Roblox was closed after launch, refuse to start
        if not self.is_roblox_running():
            self.show_message('Roblox is not running. Please start Roblox and try again.')
            return

        self.lagswitch_active = True
        self.turn_on_lag_switch()

        if self.settings['AutoTurnOff']:
            self.lagswitch_cycle_event.clear()
            threading.Thread(target=self.lagswitch_cycle_loop, daemon=True).start()

    def deactivate_lagswitch(self) -> None:
        self.lagswitch_active = False
        self.lagswitch_cycle_event.set()
        self.stop_anti_timeout_countdown()
        self.turn_off_lag_switch()

    def lagswitch_cycle_loop(self) -> None:
        while self.lagswitch_active and not self.lagswitch_cycle_event.is_set():
            if self.lagswitch_cycle_event.wait(self.timer_duration):
                break

            self.turn_off_lag_switch()

            if self.lagswitch_cycle_event.wait(self.reactivation_duration):
                break

            if self.lagswitch_active:
                if self.settings['AutoTurnBackOn']:
                    self.turn_on_lag_switch()
                else:
                    self.lagswitch_active = False
                    break

    def turn_on_lag_switch(self) -> None:
        self.block_flag = True
        self.update_firewall_rules('block')
        self.update_status_label()
        self.start_anti_timeout_countdown()

    def turn_off_lag_switch(self) -> None:
        self.block_flag = False
        self.update_firewall_rules('delete')
        self.update_status_label()
        self.stop_anti_timeout_countdown()

    def toggle_block(self, event) -> None:
        if event.name != self.settings['Keybind']:
            return
        if self.lagswitch_active:
            self.deactivate_lagswitch()
        else:
            self.activate_lagswitch()

    # ---------------- Helpers ----------------

    def update_status_label(self) -> None:
        self.status_label.configure(
            text='LagSwitch on.' if self.block_flag else 'LagSwitch off.',
            text_color='green' if self.block_flag else 'red'
        )

    def update_timer_duration(self, value: float) -> None:
        self.timer_duration = float(value)
        self.timer_label.configure(text=f"{self.timer_duration:.1f}s")
        if self.lagswitch_active and self.block_flag and self.settings['AutoTurnOff']:
            self.start_anti_timeout_countdown()

    def update_reactivation_duration(self, value: float) -> None:
        self.reactivation_duration = float(value)
        self.reactivation_label.configure(text=f"{self.reactivation_duration:.1f}s")

    def update_auto_turnoff(self) -> None:
        self.settings['AutoTurnOff'] = self.auto_turnoff_var.get()
        # If they turn Anti-Timeout off while running, stop the countdown display
        if not self.settings['AutoTurnOff']:
            self.stop_anti_timeout_countdown()
        elif self.lagswitch_active and self.block_flag:
            self.start_anti_timeout_countdown()

    def update_auto_turnbackon(self) -> None:
        self.settings['AutoTurnBackOn'] = self.auto_turnbackon_var.get()

    def change_keybind(self) -> None:
        self.keybind_label.configure(text='Press a key...')
        keyboard.on_press(self.set_keybind)

    def set_keybind(self, event) -> None:
        key = event.name
        self.settings['Keybind'] = key
        self.keybind_label.configure(text=f"Keybind: {key}")
        keyboard.unhook_all()
        keyboard.on_press_key(key, self.toggle_block)

    def setup_keybind(self) -> None:
        keyboard.on_press_key(self.settings['Keybind'], self.toggle_block)

    def update_firewall_rules(self, action: str) -> None:
        try:
            proc = next(
                p for p in psutil.process_iter(['name', 'exe'])
                if (p.info.get('name') or '').lower() == 'robloxplayerbeta.exe'
            )
            exe = proc.exe()

            if action == 'block':
                sp.run(
                    ['netsh', 'advfirewall', 'firewall', 'add', 'rule',
                     f'name={RULE_NAME}', 'dir=out', 'action=block',
                     f'program={exe}'],
                    creationflags=sp.CREATE_NO_WINDOW
                )
            else:
                sp.run(
                    ['netsh', 'advfirewall', 'firewall', 'delete', 'rule',
                     f'name={RULE_NAME}'],
                    creationflags=sp.CREATE_NO_WINDOW
                )
        except Exception:
            # If Roblox is closed mid-run, just fail silently (like your original)
            pass

    def run(self) -> None:
        atexit.register(self.exit_handler)
        self.root.mainloop()

    def exit_handler(self) -> None:
        self.lagswitch_cycle_event.set()
        self.update_firewall_rules('delete')


if __name__ == '__main__':
    try:
        LeafLag().run()
    except Exception:
        pass
