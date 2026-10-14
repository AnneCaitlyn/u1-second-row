# U1 Hub board not detected / connection interrupted | Snapmaker Wiki

Source: https://wiki.snapmaker.com/en/snapmaker_u1/troubleshooting/hub-board-connection-issue

# Terminology

[img https://wiki.snapmaker.com/u1/u1_hub-board_position.jpg]
 Hub Board 

Hub Board is the intermediate interface module that connects the toolhead to the main control board. It is related to toolhead power supply, firmware upgrades, and docking status detection.

# Issue Description

 The machine screen displays the following error:

 Hub board not detected : This means the Hub board was not powered on during system startup.

[img https://wiki.snapmaker.com/u1/error-code_0003-0522-0101-0006_en.png]

 Hub board connection interrupted : This means the Hub board was powered on normally during system startup, but it suddenly lost power after the system started.

[img https://wiki.snapmaker.com/u1/error-code_0003-0522-0100-0008_en.png]

 Special Cases 

 Under normal circumstances, when the 0003-0522-0101-0006 / 0003-0522-0100-0008 error occurs, the toolhead's internal indicator light will still turn on:

 In rare cases, if all toolheads suddenly lose power after system startup, this will be indicated by all toolhead internal indicator lights being off, and the 0003-0522-0100-0008 error will also appear.

 If you encounter this situation, please refer to No Toolhead Detected to troubleshoot the issue.

# Possible Causes

 The mainboard USB cable is loose.

 The Hub board is being compressed.

# Important Notice

 Do not unplug or reconnect cables while the machine is powered on!

# Troubleshooting Steps

## 1. Check the Hub Board USB Cable

 (1) Refer to the Side Panel Removal and Installation Tutorial to remove the right side panel of the machine.

 (2) Clean the adhesive from the mainboard USB cable connector, then unplug and reseat the USB cable.

[img https://wiki.snapmaker.com/u1/u1_main-usb-cable_downside.jpg]

 (3) Remove the screws at both ends of the Hub board.

[img https://wiki.snapmaker.com/u1/hub-board-screws_side.jpg]

 (4) With the right side panel still removed, reconnect the toolhead USB cables and restart the machine.

 If the issue persists, please export the log and contact technical support.

# End Note

 If your issue remains unresolved, please contact technical support , our dedicated support team will be more than willing to assist you in resolving the issue.

 If you have any suggestions or feedback about this wiki, feel free to leave a comment below. Every piece of feedback helps us improve our documentation.
