Sound Control Board Application
==============================

This folder contains a simple Python implementation of a **sound control board**
for Microsoft Windows.  The application exposes volume sliders for every audio
device (speakers and microphones) and for every running application that plays
sound.  It also lets you monitor your microphone in real time with an
adjustable gain so you can hear yourself through your speakers or headset.  The
app also includes route-based microphone gain profiles that can be used for
per-app microphone levels when paired with virtual audio cable devices.

> ⚠️ **Important**: This project is a proof of concept written in Python.  To
> run the application on Windows you need to install several third‑party
> packages and ensure you have Python 3.8 or later installed.  Because this
> environment cannot cross‑compile Windows executables, the project is
> distributed as source code.  Follow the installation instructions below to
> run it on your Windows machine.

Installation
------------

1. Install Python 3.8 or later from [python.org](https://www.python.org/downloads/windows/).
   During installation make sure to enable the **Add Python to PATH** option.

2. Open **Command Prompt** (Win+R → `cmd`) and install the required packages:

   ```sh
   pip install pycaw comtypes sounddevice pystray pillow psutil
   ```

   * `pycaw` provides access to the Windows Core Audio API.  It uses
     COM under the hood and exposes interfaces such as
     `IAudioEndpointVolume` and `ISimpleAudioVolume` to control device and
     session volume levels【904736212477505†L49-L84】.
   * `comtypes` is a dependency of pycaw and allows Python to talk to COM.
   * `sounddevice` is used for the microphone monitor.  It captures audio from
     the default input device and immediately plays it back to the default
     output device with a gain factor that can be adjusted between 0 % and
     200 %.  It is also used by the microphone route profiles.
   * `pystray` and `pillow` add a system tray icon so that you can hide the
     main window and still access basic functionality from the notification
     area.
   * `psutil` is used internally by pycaw to query process information.

3. Download the file `sound_control_board_app.py` and place it in a folder of
   your choice.

4. Run the application by double‑clicking the file or invoking it via

   ```sh
   python sound_control_board_app.py
   ```

Usage
-----

* When the window opens it shows two sections: **Audio Devices** and
  **Application Volumes**.  Each device or application has its own slider.
  Moving a slider updates the corresponding volume in Windows immediately.  The
  sliders display the current level (in percent) and will synchronize with
  other programs such as the built‑in volume mixer.
* Check **Monitor Microphone** to start hearing yourself.  The monitor uses
  the default microphone and default output device.  Use the **Microphone
  Boost** slider below to increase or decrease the monitor volume.  The gain
  slider ranges from 0 % (silent) to 200 % (double the input level).  Note
  that the Windows Core Audio API defines session volume levels between 0.0
  and 1.0【450741797371406†L49-L83】—this monitor gain is applied in software and
  affects only the monitored audio, not the level reported to other
  applications.
* Use **Per-App Microphone Routes** to create microphone profiles with their
  own 0 % to 200 % gain sliders.  Enter an app/profile name, choose the real
  microphone as the input, choose a virtual cable playback endpoint as the
  output, add the route, then enable it.  For example, with a virtual cable
  installed, route your real mic to that cable's playback endpoint, then set
  Discord, Zoom, or another app to use the matching virtual microphone input.
  For different levels in different apps, each app needs its own virtual cable
  route.
* Use the **Language** menu to switch between English and Simplified Chinese.
  The UI will update automatically.
* When you close the window the application minimizes to the system tray.  Use
  the tray icon’s right‑click menu to show the window again or quit.

Limitations
-----------

* **Per‑application control**: The script leverages the Windows
  ``IAudioSessionManager`` and ``ISimpleAudioVolume`` interfaces to adjust
  session volumes【450741797371406†L112-L119】.  It can control the master volume of
  any application that is currently playing sound.  However, applications
  launched after the script starts may not appear in the list until the next
  refresh (every 10 seconds by default).
* **Microphone boost**: Windows exposes volume controls for capture devices via
  ``IAudioEndpointVolume``【919150765942657†L54-L67】.  These controls operate in the range
  0.0–1.0 and are shared with all applications.  Boosting the level above
  100 % is not supported by the API, so the script applies a software gain to
  the monitored signal only.  The actual microphone level reported to other
  programs remains unaffected.
* **Per-app microphone levels**: Windows does not expose a simple public API for
  setting each application's microphone intake gain directly.  The route
  feature works by creating software-gained microphone streams and sending them
  to virtual audio cable outputs.  The target apps must be manually configured
  to use those virtual microphone inputs.  A single virtual cable gives one
  shared processed microphone signal; truly different levels for multiple apps
  require multiple virtual cables or a dedicated virtual audio driver.
* **Taskbar thumbnail**: Customizing the taskbar thumbnail preview requires
  interacting with the Windows shell API and is outside the scope of this
  script.  The system tray icon provides quick access to the most important
  actions.

License
-------

This project is provided as‑is under the MIT license.  See `LICENSE` for
details.
