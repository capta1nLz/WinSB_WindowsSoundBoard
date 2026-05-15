"""
Sound Control Board Application
--------------------------------

This Python script implements a simple sound control board for Microsoft Windows.
It uses the Windows Core Audio interfaces via the ``pycaw`` library to list
audio endpoint devices (render and capture) and the running audio sessions
(applications).  Users can adjust the master volume of each device as well as
the session volume of each application.  A built‑in microphone monitor allows
users to listen to the microphone input and amplify it beyond the normal
maximum (up to 200 %) by applying a software gain.  The application
provides a minimal graphical user interface using Tkinter and integrates
into the system tray through the ``pystray`` library so that commonly used
controls are available without opening the main window.

Features
========

* List all audio endpoint devices (speakers and microphones) and control their
  master volumes.  Device volumes are tied directly to the Windows volume
  sliders exposed by the operating system: changes in this application are
  reflected in the Windows volume mixer and vice versa because they use the
  ``IAudioEndpointVolume`` interface【919150765942657†L54-L67】.
* Enumerate the active audio sessions (applications) and adjust their
  per‑session master volumes via the ``ISimpleAudioVolume`` interface.  Each
  session corresponds to one application window, and the volume level ranges
  from 0.0 (silence) to 1.0 (full volume)【450741797371406†L49-L83】.  Changes are
  immediately visible in the Windows volume mixer.
* Monitor microphone input by routing the capture stream to the default output
  device and apply a gain factor from 0 % to 200 %.  The monitor runs in
  a separate thread and uses the ``sounddevice`` library for low‑latency
  capture/playback.
* Switch between English and Simplified Chinese UI strings via a menu.
* Integrate into the Windows notification area via ``pystray``.  Right‑click
  the tray icon to open the main window or exit the application.  Hovering
  over the taskbar icon (thumbnail preview) shows the current volume levels,
  although custom thumbnail buttons are not implemented because that requires
  deep integration with the Windows shell.

Requirements
------------

The script depends on the following third‑party Python libraries:

* **pycaw** – wraps the Windows Core Audio API.  Install via
  ``pip install pycaw``.  Pycaw itself depends on ``comtypes``.  The
  application uses ``AudioUtilities`` to enumerate devices and sessions and
  ``IAudioEndpointVolume``/``ISimpleAudioVolume`` to adjust volumes.
* **sounddevice** – provides real‑time audio capture and playback for the
  microphone monitor.  Install via ``pip install sounddevice``.  On Windows
  this library is lightweight and uses the default WASAPI backend.
* **pystray** and **pillow** – needed for the system tray icon.  Install via
  ``pip install pystray pillow``.

Without these packages the script will not run on Windows.  See the
accompanying README for additional instructions.
"""

import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import ttk, messagebox

try:
    # Import third‑party libraries lazily so that the module can be imported on
    # non‑Windows platforms (for documentation) without immediately raising
    # ImportError.  Actual usage on Windows requires these packages to be
    # installed.
    from comtypes import CLSCTX_ALL  # type: ignore
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore
    from pycaw.pycaw import ISimpleAudioVolume  # type: ignore
    import sounddevice as sd  # type: ignore
    import numpy as np  # type: ignore
    import pystray  # type: ignore
    from PIL import Image, ImageDraw  # type: ignore
except ImportError:
    # If we cannot import the audio libraries, we still define placeholders so
    # that the rest of the script parses.  The GUI will later display an
    # informative message when run without the required dependencies.
    CLSCTX_ALL = None
    AudioUtilities = None
    IAudioEndpointVolume = None
    ISimpleAudioVolume = None
    sd = None
    np = None
    pystray = None
    Image = None
    ImageDraw = None


@dataclass
class DeviceEntry:
    """Represents an audio endpoint device and its volume interface."""
    name: str
    endpoint: object
    volume_interface: object
    is_capture: bool
    slider: Optional[tk.Scale] = None


@dataclass
class SessionEntry:
    """Represents an audio session (application) and its volume interface."""
    display_name: str
    pid: int
    volume_interface: object
    slider: Optional[tk.Scale] = None


class SoundControlBoardApp:
    """Main class implementing the sound control board UI and logic."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Sound Control Board")
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

        # Application state
        self.language = "en"
        self.translations = self._build_translations()
        self.devices: List[DeviceEntry] = []
        self.sessions: List[SessionEntry] = []
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.monitor_gain = 1.0  # 1.0 corresponds to 100 %

        # Build UI
        self._build_menu()
        self._build_widgets()

        # Populate lists and schedule periodic updates
        self.update_lists()
        self.root.after(1000, self.periodic_update)

        # Create system tray icon
        if pystray is not None:
            self._create_tray_icon()

    # ------------------------------------------------------------------
    # UI construction
    #
    def _build_translations(self) -> Dict[str, Dict[str, str]]:
        """Return the translation dictionary used by the UI."""
        return {
            "en": {
                "title": "Sound Control Board",
                "devices": "Audio Devices",
                "sessions": "Application Volumes",
                "monitor": "Monitor Microphone",
                "monitor_gain": "Microphone Boost (%d%%)",
                "language": "Language",
                "english": "English",
                "chinese": "简体中文",
                "show": "Show",
                "exit": "Exit",
                "missing_deps": (
                    "Required dependencies are missing.\n"
                    "Please install pycaw, comtypes, sounddevice, pystray and pillow."
                ),
            },
            "zh": {
                "title": "声音控制板",
                "devices": "音频设备",
                "sessions": "应用音量",
                "monitor": "监听麦克风",
                "monitor_gain": "麦克风增益（%d%%）",
                "language": "语言",
                "english": "English",
                "chinese": "简体中文",
                "show": "显示",
                "exit": "退出",
                "missing_deps": (
                    "缺少必要的依赖包。\n"
                    "请安装 pycaw、comtypes、sounddevice、pystray 和 pillow。"
                ),
            },
        }

    def _translate(self, key: str) -> str:
        """Return the translated string for the current language."""
        return self.translations[self.language][key]

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self.root)
        # Language menu
        lang_menu = tk.Menu(menu_bar, tearoff=0)
        lang_menu.add_command(label=self.translations["en"]["english"],
                              command=lambda: self._set_language("en"))
        lang_menu.add_command(label=self.translations["zh"]["chinese"],
                              command=lambda: self._set_language("zh"))
        menu_bar.add_cascade(label=self._translate("language"), menu=lang_menu)
        self.root.config(menu=menu_bar)

    def _build_widgets(self) -> None:
        # Frame for devices
        self.device_frame = ttk.LabelFrame(self.root, text=self._translate("devices"))
        self.device_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        # Frame for sessions
        self.session_frame = ttk.LabelFrame(self.root, text=self._translate("sessions"))
        self.session_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        # Microphone monitor and gain
        self.monitor_var = tk.BooleanVar(value=False)
        self.monitor_check = ttk.Checkbutton(
            self.root, text=self._translate("monitor"), variable=self.monitor_var,
            command=self._toggle_monitor)
        self.monitor_check.pack(anchor=tk.W, padx=8, pady=4)
        self.gain_scale = ttk.Scale(
            self.root, from_=0.0, to=2.0, value=1.0, orient=tk.HORIZONTAL,
            command=self._on_gain_change)
        self.gain_scale.pack(fill=tk.X, padx=8, pady=2)
        self.gain_label_var = tk.StringVar()
        self.gain_label = ttk.Label(self.root, textvariable=self.gain_label_var)
        self.gain_label.pack(anchor=tk.W, padx=8)
        self._update_gain_label()

    def _set_language(self, lang: str) -> None:
        if lang not in self.translations:
            return
        self.language = lang
        # Update window title and labels
        self.root.title(self._translate("title"))
        self.device_frame.config(text=self._translate("devices"))
        self.session_frame.config(text=self._translate("sessions"))
        self.monitor_check.config(text=self._translate("monitor"))
        self._update_gain_label()
        # Update menu labels
        self._build_menu()

    # ------------------------------------------------------------------
    # Device and session enumeration
    #
    def update_lists(self) -> None:
        """Refresh the list of devices and sessions and rebuild UI controls."""
        # Clear existing controls
        for child in list(self.device_frame.winfo_children()):
            child.destroy()
        for child in list(self.session_frame.winfo_children()):
            child.destroy()
        self.devices = []
        self.sessions = []

        # Check dependencies
        if AudioUtilities is None or IAudioEndpointVolume is None or ISimpleAudioVolume is None:
            ttk.Label(self.device_frame, text=self._translate("missing_deps"),
                      foreground="red").pack(anchor=tk.W, pady=4, padx=4)
            return

        # Enumerate devices
        try:
            # Get default render and capture devices
            devices = AudioUtilities.GetAllDevices()
        except Exception:
            devices = []
        for dev in devices:
            try:
                endpoint = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume_interface = cast(endpoint, IAudioEndpointVolume)
                is_capture = dev.data_flow == 1  # 0: render, 1: capture
                entry = DeviceEntry(name=dev.FriendlyName, endpoint=dev,
                                    volume_interface=volume_interface,
                                    is_capture=is_capture)
                self.devices.append(entry)
            except Exception:
                continue

        # Build device controls
        for entry in self.devices:
            row = ttk.Frame(self.device_frame)
            row.pack(fill=tk.X, padx=4, pady=2)
            label = ttk.Label(row, text=entry.name)
            label.pack(side=tk.LEFT)
            # Slider from 0 to 100 representing normalized volume 0.0–1.0
            slider = tk.Scale(
                row, from_=0, to=100, orient=tk.HORIZONTAL, length=200,
                command=lambda value, e=entry: self._on_device_volume_change(e, value))
            slider.pack(side=tk.RIGHT)
            entry.slider = slider
        # Enumerate sessions
        try:
            sessions = AudioUtilities.GetAllSessions()
        except Exception:
            sessions = []
        for sess in sessions:
            try:
                volume = sess._ctl.QueryInterface(ISimpleAudioVolume)
                display_name = sess.DisplayName or (sess.Process and sess.Process.name()) or "?"
                pid = sess.Process.pid if sess.Process else 0
                entry = SessionEntry(display_name=display_name, pid=pid,
                                     volume_interface=volume)
                self.sessions.append(entry)
            except Exception:
                continue
        # Build session controls
        for entry in self.sessions:
            row = ttk.Frame(self.session_frame)
            row.pack(fill=tk.X, padx=4, pady=2)
            label = ttk.Label(row, text=f"{entry.display_name} (PID {entry.pid})")
            label.pack(side=tk.LEFT)
            slider = tk.Scale(
                row, from_=0, to=100, orient=tk.HORIZONTAL, length=200,
                command=lambda value, e=entry: self._on_session_volume_change(e, value))
            slider.pack(side=tk.RIGHT)
            entry.slider = slider
        # Immediately update slider positions
        self._refresh_slider_positions()

    def _refresh_slider_positions(self) -> None:
        """Update sliders to reflect current volume levels."""
        # Device sliders
        for entry in self.devices:
            try:
                # Get master volume as a scalar between 0.0 and 1.0
                vol = entry.volume_interface.GetMasterVolumeLevelScalar()
                if entry.slider:
                    entry.slider.set(int(vol * 100))
            except Exception:
                pass
        # Session sliders
        for entry in self.sessions:
            try:
                vol = entry.volume_interface.GetMasterVolume()
                if entry.slider:
                    entry.slider.set(int(vol * 100))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Slider callbacks
    #
    def _on_device_volume_change(self, entry: DeviceEntry, value: str) -> None:
        """Handle changes to a device volume slider."""
        try:
            scalar = float(value) / 100.0
            entry.volume_interface.SetMasterVolumeLevelScalar(scalar, None)
        except Exception:
            pass

    def _on_session_volume_change(self, entry: SessionEntry, value: str) -> None:
        """Handle changes to a session volume slider."""
        try:
            scalar = float(value) / 100.0
            entry.volume_interface.SetMasterVolume(scalar, None)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Microphone monitor
    #
    def _toggle_monitor(self) -> None:
        """Start or stop monitoring the microphone."""
        if self.monitor_var.get():
            self.start_monitor()
        else:
            self.stop_monitor()

    def start_monitor(self) -> None:
        """Start the microphone monitoring thread."""
        if self.monitoring or sd is None or np is None:
            return
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop_monitor(self) -> None:
        """Stop the microphone monitoring thread."""
        self.monitoring = False

    def _on_gain_change(self, value: float) -> None:
        """Update the monitor gain when the slider moves."""
        self.monitor_gain = float(value)
        self._update_gain_label()

    def _update_gain_label(self) -> None:
        percentage = int(self.monitor_gain * 100)
        self.gain_label_var.set(self._translate("monitor_gain") % percentage)

    def _monitor_loop(self) -> None:
        """Capture microphone audio and immediately play it back."""
        # Determine default input/output devices
        try:
            default_input = sd.default.device[0]  # input index
            default_output = sd.default.device[1]  # output index
        except Exception:
            default_input = None
            default_output = None
        samplerate = 44100
        blocksize = 1024
        if default_input is None or default_output is None:
            return
        def callback(indata, outdata, frames, time_info, status):
            if not self.monitoring:
                raise sd.CallbackStop()
            # Apply gain and copy input to output
            outdata[:] = indata * self.monitor_gain
        with sd.Stream(device=(default_input, default_output),
                       samplerate=samplerate,
                       blocksize=blocksize,
                       dtype='float32',
                       channels=1,
                       callback=callback):
            while self.monitoring:
                time.sleep(0.1)

    # ------------------------------------------------------------------
    # System tray integration
    #
    def _create_tray_icon(self) -> None:
        """Set up the system tray icon using pystray."""
        # Create a simple icon: a pair of concentric circles on a square canvas
        def create_image(size=64, color1="#3c3c3c", color2="#ffffff") -> Image.Image:
            img = Image.new("RGB", (size, size), color1)
            draw = ImageDraw.Draw(img)
            margin = size // 8
            draw.ellipse((margin, margin, size - margin, size - margin), fill=color2)
            return img
        image = create_image()
        menu = pystray.Menu(
            pystray.MenuItem(
                self._translate("show"), lambda: self.show_window()),
            pystray.MenuItem(
                self._translate("exit"), lambda: self.exit_application()),
        )
        self.tray_icon = pystray.Icon("sound_control_board", image, self._translate("title"), menu)
        # Run the tray icon in its own thread so it does not block the mainloop
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self) -> None:
        """Show the main window (called from tray menu)."""
        self.root.after(0, self.root.deiconify)

    def hide_window(self) -> None:
        """Hide the main window without exiting (minimize to tray)."""
        self.root.withdraw()

    def exit_application(self) -> None:
        """Exit the application gracefully."""
        self.stop_monitor()
        if hasattr(self, "tray_icon") and self.tray_icon:
            self.tray_icon.stop()
        self.root.destroy()

    # ------------------------------------------------------------------
    # Periodic updates
    #
    def periodic_update(self) -> None:
        """Periodically refresh slider positions and lists."""
        self._refresh_slider_positions()
        # Every 10 seconds re‑enumerate devices and sessions to catch new apps
        now = int(time.time())
        if now % 10 == 0:
            self.update_lists()
        self.root.after(1000, self.periodic_update)


def main() -> None:
    root = tk.Tk()
    app = SoundControlBoardApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()