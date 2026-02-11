# gaze_capture
Record, process and transmit gaze data.


# Disconnect eye-tracker from Linux host
systemctl stop tobii-runtime-TOBIIPROFUSIONC.service



# Link from Windows to WSL

PS:> usbipd list
Connected:
BUSID  VID:PID    DEVICE                                                        STATE
2-2    045e:0c1e  Surface Camera Front, Surface IR Camera Front                 Not shared
2-5    2104:0604  EyeChip                                                       Not shared
2-10   8087:0029  Intel(R) Wireless Bluetooth(R)                                Not shared

**Admin** 
PS:> usbipd bind --busid 2-5
Connected:
BUSID  VID:PID    DEVICE                                                        STATE
2-2    045e:0c1e  Surface Camera Front, Surface IR Camera Front                 Not shared
2-5    2104:0604  EyeChip                                                       Shared
2-10   8087:0029  Intel(R) Wireless Bluetooth(R)                                Not shared

PS:> usbipd attach --wsl --busid 2-5
usbipd: info: Using WSL distribution 'Ubuntu' to attach; the device will be available in all WSL 2 distributions.
usbipd: info: Detected networking mode 'nat'.
usbipd: info: Using IP address 172.24.80.1 to reach the host.

If you can't, it's because Windows is connected to eye tracker, go to task monitor and close tasks from Tobii.


- Get info
    - SN
    - Address
    - Frequency
    - MORE

- Set Display Area
    - 
    - Save as global setting
    - Load global setting

- Calibration (https://developer.tobiipro.com/commonconcepts/calibration.html)
    - Enter calibration mode
        - Custom implementation (draw chosen points ourselves)
        - ET Manager (https://developer.tobiipro.com/eyetrackermanager/etm-sdk-integration.html)
                     (https://developer.tobiipro.com/tobii.research/python/reference/2.1.0.3-alpha-gd8b35e1b/call_eyetracker_manager_8py-example.html)
    - Save calibration
    - Load calibration
    - Check calibration
        - Generate results from calibration (image https://developer.tobiipro.com/images/sdk-images/CalibrationPlot.png)

- [LATER] Test mode
    - Show moving target
    - SHIFT to show in real-time (faint to not distract)
    - ENTER to replay
    - ESC to exit

- Capture data
    - Pupil

- Export data (sinks)
    - CSV
    - ZMQ
    - HTTP (bundle)







Supported eye trackers:
- Tobii Pro Fusion
- Dummy


Interfaces:
- GUI
- Headless (send commands)






https://developer.tobiipro.com/tobii.research/python/reference/2.1.0.3-alpha-gd8b35e1b/time_synchronization_data_8py-example.html
https://developer.tobiipro.com/tobii.research/python/reference/2.1.0.3-alpha-gd8b35e1b/notifications_8py-example.html