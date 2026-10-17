; Inno Setup script: turns dist\Jarvis into JarvisSetup.exe
; build.bat runs this automatically if Inno Setup 6 is installed.

#define AppName "Jarvis"
#define AppVersion "0.1.0"

[Setup]
AppId={{CF14F4C1-93D4-46E1-8FA9-A46FAAE0E9FB}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Quincy Williams
DefaultDirName={localappdata}\Programs\Jarvis
DefaultGroupName=Jarvis
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=JarvisSetup
SetupIconFile=assets\jarvis.ico
UninstallDisplayIcon={app}\Jarvis.exe
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start Jarvis when Windows starts"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "dist\Jarvis\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Jarvis"; Filename: "{app}\Jarvis.exe"
Name: "{autodesktop}\Jarvis"; Filename: "{app}\Jarvis.exe"; Tasks: desktopicon
Name: "{userstartup}\Jarvis"; Filename: "{app}\Jarvis.exe"; Tasks: startup

[Run]
Filename: "{app}\Jarvis.exe"; Description: "Launch Jarvis"; Flags: nowait postinstall skipifsilent
