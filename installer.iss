; Inno Setup script: turns dist\Drexya into DrexyaSetup.exe
; build.bat runs this automatically if Inno Setup 6 is installed.

#define AppName "Drexya"
#define AppVersion "0.1.0"

[Setup]
AppId={{CF14F4C1-93D4-46E1-8FA9-A46FAAE0E9FB}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Quincy Williams
DefaultDirName={localappdata}\Programs\Drexya
DefaultGroupName=Drexya
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=DrexyaSetup
SetupIconFile=assets\jarvis.ico
UninstallDisplayIcon={app}\Drexya.exe
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start Drexya when Windows starts"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "dist\Drexya\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Drexya"; Filename: "{app}\Drexya.exe"
Name: "{autodesktop}\Drexya"; Filename: "{app}\Drexya.exe"; Tasks: desktopicon
Name: "{userstartup}\Drexya"; Filename: "{app}\Drexya.exe"; Tasks: startup

[Run]
Filename: "{app}\Drexya.exe"; Description: "Launch Drexya"; Flags: nowait postinstall skipifsilent
