; Inno Setup script for the Windows installer. Built by .github/workflows/installers.yml:
;   iscc /DAppVersion=0.2.0 packaging\windows\puppetcam.iss
; Installs for the current user only: no admin rights, no UAC prompt.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1B7C5E-4D0A-4B8E-9C61-3A2F9D7E5B10}
AppName=Puppetcam
AppVersion={#AppVersion}
AppPublisher=Cesare Davide Pace
AppPublisherURL=https://github.com/cesaredavidepace/puppetcam
AppSupportURL=https://github.com/cesaredavidepace/puppetcam/issues
DefaultDirName={localappdata}\Programs\Puppetcam
DefaultGroupName=Puppetcam
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=Puppetcam-{#AppVersion}-windows-setup
SetupIconFile=..\..\build\icons\icon.ico
UninstallDisplayIcon={app}\puppetcam.exe
LicenseFile=..\..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "autostart"; Description: "Start Puppetcam when I log in"; Flags: unchecked
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\puppetcam\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Puppetcam"; Filename: "{app}\puppetcam.exe"
Name: "{group}\Uninstall Puppetcam"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Puppetcam"; Filename: "{app}\puppetcam.exe"; Tasks: desktopicon

[Registry]
; Same value as puppetcam/autostart.py, so the tray's "Start at login" shows it checked.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "puppetcam"; ValueData: """{app}\puppetcam.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\puppetcam.exe"; Description: "Start Puppetcam now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM puppetcam.exe /F"; Flags: runhidden; RunOnceId: "StopPuppetcam"

[Code]
// The tray's "Start at login" may have added the Run value after install: clean it on uninstall.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'puppetcam');
end;
