# U1 Pogopin contact anomaly | Snapmaker Wiki

Source: https://wiki.snapmaker.com/en/snapmaker_u1/troubleshooting/pogopin_contact_anomaly

# 💡 Compatibility

 This article applies to the following models. Please note when referencing:

 Model: U1

# 📝 Issue Description

 After printing is complete, the following error appears on the screen:

[img https://wiki.snapmaker.com/u1/error-code_0001-0523-0000-0048_en.png]

# 📕 Terminology

[img https://wiki.snapmaker.com/u1/u1_pogo-pin&solid-pin_connect.jpg]

# 🛠️ Troubleshooting Steps

 1. Pogo Pin & Solid Pin Contamination 

Use a lint-free cloth and alcohol to clean the Pogo Pin & Solid Pin as demonstrated.

 The lint-free cloth must be wrapped around your fingers and must not hang loose, to avoid contact with the grease on the steel balls.

 2. Pogo Pin Stuck 

Wrap a lint-free cloth around your finger and press the Pogo Pin. If the Pogo Pin cannot be pressed down or does not spring back after being pressed, the toolhead PCB needs to be replaced.

 Each Pogo Pin has three pins. Check them one by one.

 3. Insufficient Pogo Pin Compression Travel (I have access to a caliper) 

With the toolhead top cover and part cooling fan cover removed, manually pick the toolhead and use a caliper to measure the distance between the two points shown in the diagram.

If the measured value exceeds the reference range, please contact technical support .

Remove toolhead top cover: 0:09—1:22 

Remove part cooling fan cover: 0:20—0:40 

[img https://wiki.snapmaker.com/u1/u1_pogopin&solidpin_distance.jpg]

 3. Insufficient Pogo Pin Compression Travel (I do not have access to a caliper) 

Please check whether there are any protruding screws on the back of the toolhead swapper, and whether there are any foreign objects in the 3 pin slots.

[img https://wiki.snapmaker.com/u1/u1_toolhead-swapper-screws_back.jpg]

[img https://wiki.snapmaker.com/u1/u1_female-mount_pin-position.jpg]

# 👨🏼‍💻 Remote Assistance

 If your machine does not match any of the above situations, please provide the information below and contact technical support .

 1. Order Number 
 Purchased from Kickstarter: Please provide your Backer Number

 Purchased from the official website: Please provide the order number starting with "SM"

 Purchased from a distributor: Please provide the distributor name and order number

 Purchased from Tmall/JD flagship store: Please provide the store order number

 2. Machine Serial Number 

 Located at the bottom of the machine's back panel. Please provide both the S/N and Verification Code .

[img https://wiki.snapmaker.com/u1/sn_position.jpg]

 3. Pogo Pin & Solid Pin Photos 

 Clear photos will help speed up the resolution of your issue. It is recommended to provide photos following the examples below, and name them to indicate which toolhead each photo corresponds to:

[img https://wiki.snapmaker.com/u1/solidpin.jpg]

[img https://wiki.snapmaker.com/u1/pogopin_1234.jpg]

 4. Perform toolhead swap test 

 Download and Run Toolhead swap test gcode .

 After the G-code has finished running, please tap the error code and record error count message.

[img https://wiki.snapmaker.com/u1/swap-all-gcode_result_en.png]
