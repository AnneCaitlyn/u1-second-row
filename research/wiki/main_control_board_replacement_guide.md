# U1 main control board replacement guide | Snapmaker Wiki

Source: https://wiki.snapmaker.com/en/snapmaker_u1/troubleshooting/main_control_board_replacement_guide

# Overview

## Location

 The main control board is located at the right inner panel of the machine, and replacing it requires removing the right panel.

[img https://wiki.snapmaker.com/u1/u1_main-control-board_location.png]

## Terminology

 Different from our official term, some people may use the following terms to describe this component:

 Motherboard

 mainboard

 Brain board

 Controller

 Printer control board

## Difficulty and Time Estimate

 Difficulty ： ★★★ ☆☆ (moderate)

 Estimated Time ：20 minutes

## Where to Buy

 US: https://us.snapmaker.com/products/main-control-board-for-snapmaker-u1 

EU: https://eu.snapmaker.com/products/main-control-board-for-snapmaker-u1 

Global: https://shop.snapmaker.com/products/main-control-board-for-snapmaker-u1 

## Tools and Parts Required

 H2.0 hex key

 New main control board

## Before You Start

 After replacing the main control board, the machine will use the default toolhead swapping coordinates built into the new board. In rare cases, this may cause a toolhead swapping anomaly. Therefore, we recommend backing up the toolhead swapping coordinates from the original control board before replacement. If a swapping issue occurs later, you can refer to this backup and restore the original coordinate data.

 Additionally, if there is any homing_calibrated_origin data available, you may back it up as well. If this data does not exist, it can be safely ignored.

 Please follow the steps below for detailed instructions.

 (1) Check the machine IP in Settings > Wi-Fi, then enter the IP address in your computer browser.

[img https://wiki.snapmaker.com/u1/z-hop_noise_03.png]

 (2) On the Fluidd page, click Configuration, then go to the persistent folder and download the extruder_config.json file and the homing_calibrated_origin.json file (if available).

[img https://wiki.snapmaker.com/u1/pixpin_2026-02-02_20-03-11.jpg]

 (3) Once the main control board replacement is complete, re-upload the backup files to the /persistent folder.

[img https://wiki.snapmaker.com/u1/overwrite-coordinates-and-origin_en.jpg]

# Part 1. Remove the panels

## Step 1. Unload filament from toolheads 3 and 4

 Tap the highlighted area on the screen.

[img https://wiki.snapmaker.com/u1/u1_unload_filament1.png]

 Tap "Unload Mode".

[img https://wiki.snapmaker.com/u1/u1_unload_filament2.png]

 Select toolheads 3 and 4, then tap "Unload".

[img https://wiki.snapmaker.com/u1/u1_unload_filament3.png]

 Wait for the machine to complete the unloading.

[img https://wiki.snapmaker.com/u1/u1_unload_filament4.png]

 Turn the spool to retract the remaining filament.

[img https://wiki.snapmaker.com/u1/u1_main-control-board_unload_filament4.png]

 Remove the spools and spool holders 3 and 4.

[img https://wiki.snapmaker.com/u1/u1_main-control-board_unload_filament5.jpg]

## Step 2. Power off the machine

 Before proceeding, please turn off the machine and unplug the power cable!

[img https://wiki.snapmaker.com/u1/u1_power_off_the_machine.png]

## Step 3. Remove the filament feeder on right side

 Press the clip at the marked location.

[img https://wiki.snapmaker.com/u1/u1_hub_board_step5_remove_the_filament_feeder_on_both_sides1.png]

 While pressing the clip, slide the filament feeder in the indicated direction to remove it.

[img https://wiki.snapmaker.com/u1/u1_hub_board_step5_remove_the_filament_feeder_on_both_sides2.png]

 Next, press point 1 as shown in the image to disconnect the filament feeder cable.

[img https://wiki.snapmaker.com/u1/u1_hub_board_step5_remove_the_filament_feeder_on_both_sides3.png]

 Complete.

[img https://wiki.snapmaker.com/u1/u1_hub_board_step5_remove_the_filament_feeder_on_both_sides4.png]

## Step 4. Disconnect USB cables

 Use a H2.0 hex key to remove the 8 screws from the 4 USB cables, then unplug the cables.

[img https://wiki.snapmaker.com/u1/u1_main-control-board_disconnect_usb_cable1.png]

[img https://wiki.snapmaker.com/u1/u1_main-control-board_disconnect_usb_cable2.png]

## Step 5. Remove the top cover panel

 Take out the silicone plugs from all four corners of the top cover panel.

[img https://wiki.snapmaker.com/u1/u1_hub_board_step6_remove_the_top_cover1.png]

 Use a H2.0 hex key to remove the 4 screws beneath the plugs.

[img https://wiki.snapmaker.com/u1/u1_hub_board_step6_remove_the_top_cover2.png]

## Step 6. Remove the right panel

 Slightly shift the top cover panel as shown in the image, then remove the four marked screws.

[img https://wiki.snapmaker.com/u1/u1_hub_board_step_8._remove_the_right_panel1.png]

 Remove screws 5 and 6 located inside the spool holder holes.

[img https://wiki.snapmaker.com/u1/u1_hub_board_step_8._remove_the_right_panel2.png]

 Then remove screws 7 and 8 on the right inner panel.

[img https://wiki.snapmaker.com/u1/
u1_main-control-board_remove_right_plastic-panel3.png]

 Pass the filament feeder cable through position 1 and disconnect the two RFID cables at position 2, then remove the right panel.

[img https://wiki.snapmaker.com/u1/u1_hub_board_step_8._remove_the_right_panel4.png]

# Part 2. Replace the main control board

## Step 7. Remove the old main control board

 Disconncet the 16 cables from main control board.

[img https://wiki.snapmaker.com/u1/ 
u1_main-control-board_remove1.png]

 For the FFC cables at positions 2, 3, and 16, lift the black flip cover slowly before removing them.

[img https://wiki.snapmaker.com/u1/ 
u1_main-control-board_remove2.jpg]

 Use the H2.0 hex key to unscrew the 4 screws, then remove the old main control board.

[img https://wiki.snapmaker.com/u1/ 
u1_main-control-board_remove3.png]

## Step 8. Install the new main control board

 Install the new main control board, use the H2.0 hex key to tighten the 4 screws.

[img https://wiki.snapmaker.com/u1/ 
u1_main-control-board_remove3.png]

 Reconnect the cables to the main control board.

[img https://wiki.snapmaker.com/u1/ 
u1_main-control-board_remove1.png]

 | 

 | No. 
 | Cable 
 | No. 
 | Cable 

 | 1 
 | LAVA WIFI Antenna 
 | 9 
 | Right Motor Cable 

 | 2 
 | Camera Control Cable 
 | 10 
 | Z-axis Motor Cable 

 | 3 
 | Screen Control Cable 
 | 11 
 | Main Board Power Cable 

 | 4 
 | Light Strip Control Cable 
 | 12 
 | Heated Bed Control Cable 

 | 5 
 | USB Transfer Cable 
 | 13 
 | USB Expansion Cable 

 | 6 
 | Main Control Board—HUB Board Connection Cable 
 | 14 
 | CAN Board Expansion Cable 

 | 7 
 | Chamber Temperature NTC 
 | 15 
 | Filament Feeder Cable 

 | 8 
 | Left Motor Cable 
 | 16 
 | RFID Transfer Cable 

# Part 3. Reassemble the machine

## Step 9. Reinstall the right panel

 Reconnect the RFID cables at position 1, pass the filament feeder cable through position 2, then install the right panel.

[img https://wiki.snapmaker.com/u1/u1_main-control-board_reinstall_right_plastic-panel1.png]

[img https://wiki.snapmaker.com/u1/u1_main-control-board_reinstall_right_plastic-panel2.jpg]

 Use the H2.0 hex key to tighten the 8 screws of the right panel.

[img https://wiki.snapmaker.com/u1/u1_hub_board_step_8._remove_the_right_panel1.png]

[img https://wiki.snapmaker.com/u1/u1_hub_board_step_8._remove_the_right_panel2.png]

[img https://wiki.snapmaker.com/u1/
u1_main-control-board_remove_right_plastic-panel3.png]

## Step 10. Reinstall filament feeder and spools

 Reconnect the filament feeder cable and organize it as shown.

[img https://wiki.snapmaker.com/u1/ 
u1_main-control-board_reinstall_filament_feeder2.png]

[img https://wiki.snapmaker.com/u1/ 
u1_main-control-board_reinstall_filament_feeder3.png]

 Align the feeder clips with the corresponding positions, then push the feeder into place in the direction shown to complete installment.

[img https://wiki.snapmaker.com/u1/ 
u1_main-control-board_reinstall_filament_feeder4.png]

[img https://wiki.snapmaker.com/u1/ 
u1_main-control-board_reinstall_filament_feeder5.png]

 Reinstall the spools and spool holders.

[img https://wiki.snapmaker.com/u1/ 
u1_main-control-board_reinstall_spool.png]

## Step 11. Reinstall the top cover panel

 Install the top cover panel, use the H2.0 hex key to tighten the 4 screws.

[img https://wiki.snapmaker.com/u1/u1_hub_board_step6_remove_the_top_cover2.png]

 Install the silicone plugs.

[img https://wiki.snapmaker.com/u1/u1_hub_board_step6_remove_the_top_cover1.png]

## Step 12. Reconnect USB cables

 Reconnect the USB cables, then use the H2.0 hex key to tighten the 8 screws.

[img https://wiki.snapmaker.com/u1/u1_main-control-board_disconnect_usb_cable1.png]

## Step 13. Insert filament

 Power on the machine and insert the filaments into the corresponding feeder ports in sequence.

[img https://wiki.snapmaker.com/u1/u1_power_on.jpg]

[img https://wiki.snapmaker.com/u1/u1_main-control-board_insert_filament.jpg]

# Reach out to Snapmaker Support

 After following the troubleshooting steps, if you find it difficult to resolve your issue, kindly submit a support ticket through https://snapmaker.formcrafts.com/u1-troubleshooting-request and share your troubleshooting results with some pictures/videos.

 Our dedicated support team will be more than willing to assist you in resolving the issue.
