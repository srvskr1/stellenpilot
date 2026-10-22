; Inno Setup script for the Stellenpilot Windows installer. Built by .github/workflows/windows.yml.
; Per user install, no administrator rights needed. Your workspace (Documents\Stellenpilot) is never touched.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E1C2F4B-7A3D-4C5E-9B2A-5D8F1E0C3A71}
AppName=Stellenpilot
AppVersion={#AppVersion}
AppVerName=Stellenpilot {#AppVersion}
AppPublisher=Stellenpilot (open source)
AppPublisherURL=https://github.com/srvskr1/stellenpilot
AppSupportURL=https://github.com/srvskr1/stellenpilot/issues
DefaultDirName={localappdata}\Programs\Stellenpilot
DefaultGroupName=Stellenpilot
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Stellenpilot-Setup-{#AppVersion}
SetupIconFile=..\stellenpilot\web\icon.ico
UninstallDisplayIcon={app}\Stellenpilot.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
LicenseFile=..\LICENSE

[Tasks]
Name: "desktopicon"; Description: "Put a Stellenpilot icon on the desktop"; GroupDescription: "Icons:"

[Files]
Source: "..\dist\Stellenpilot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Stellenpilot"; Filename: "{app}\Stellenpilot.exe"; Comment: "Your local AI job assistant"
Name: "{autodesktop}\Stellenpilot"; Filename: "{app}\Stellenpilot.exe"; Comment: "Your local AI job assistant"; Tasks: desktopicon

[Run]
Filename: "{app}\Stellenpilot.exe"; Description: "Start Stellenpilot now"; Flags: nowait postinstall skipifsilent
; A one click update from the dashboard runs this installer silently: start the new version afterwards.
Filename: "{app}\Stellenpilot.exe"; Flags: nowait skipifnotsilent

[UninstallRun]
; Remove the daily search task, if one was set up, so nothing runs after uninstalling.
Filename: "schtasks.exe"; Parameters: "/Delete /TN ""Stellenpilot daily search"" /F"; Flags: runhidden; RunOnceId: "RemoveTask"
