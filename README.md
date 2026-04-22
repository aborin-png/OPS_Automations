# OPS Automations

# Overview

This is an OPS repo that contains automation code for day to day testing and operations involving basic data collection from robots.

# Getting Started

Depending on the OS that is being used, the installation method may vary. Ultimately, all that is needed is to clone the repo in any location, preferably in a dedicated folder, and run the downloaded executable.

>[!WARNING]
>On first run of any script, a default config will be created if a config does not already exist.
>
> **However, the location of the Config.json file CANNOT be changed or the script will NOT work.**
>
>Likewise, **do NOT move the executable files to different locations after cloning the repo**. For useful organization tips, refer to [Organization Tips](https://github.com/aborin-png/OPS_Automations/tree/Releases#organization-tips)

## Linux

1. Make sure that your system is up to date using `sudo apt update & sudo apt upgrade -y`
   
2. Create a folder in any directory desired and name it what you like, then cd into the newly created directory.
  
   This can be done with the terminal by typing: `mkdir <NAME OF NEW DIRECTORY>` then `cd <NAME OF NEW DIRECTORY>`
   
3. Clone the repo into this newly created directory using: `git clone https://github.com/aborin-png/OPS_Automations.git`
   
4. Navigate to the location of the script you would like to run and run the script.

   For example when trying to run Sheet Editor:

   Run `cd OPS_Automations/Ubuntu/Sheets_Automation/` to navigate to the correct directory then run the script by using `./Sheets_editor`


## Windows

1. Create a new filder wherever is most comfortable and name it what you like.
   
2. Confirm that git is installed and Windows can access it.

   This can be done by opening a terminal (Win + R) and running the command: `git --version`

   If nothing appears or an error appears then download git from the official [git website](https://github.com/git-for-windows/git/releases/download/v2.54.0.windows.1/Git-2.54.0-64-bit.exe).
   
3. Once git is confirmed installed:
   - Open the folder created earlier
   - Hold Shift and Right click anywhere in the folder
   - Click "Open Command window here"
     
4. In the terminal that has opened up, type `git clone https://github.com/aborin-png/OPS_Automations.git` to clone the repo

5. Finally, navigate to whichever program you want to run and simply double click the .exe file to run the scripts


# Organization Tips

## Shortcuts

Since the executable and Config.json files cannot be moved once they are cloned from the repo, shortcuts can make organization and ease of access significantly better.

### Linux

1. Navigate to the location of the executable you want to make a shortcut of using your file system (not using the terminal)
   
2. Hold CTRL + SHIFT then click and drag the executable file to your desktop

3. Once the file is created, it can be renamed and moved to any location that is most comfortable

4. (Optional) Repeat this process for the Config.json file

### Windows

1. Navigate to the location of the executable you want to make a shortcut of

2. Right click on the executable and click "Create Shortcut"

3. This new file can now be moved anywhere on the computer

4. (Optional) Repeat this process for the Config.json file
