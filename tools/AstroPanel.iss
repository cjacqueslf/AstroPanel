#ifndef AppVersion
  #error AppVersion must be supplied by build_installer.ps1
#endif

[Setup]
AppId={{D93CC968-E962-440F-994C-9826DB4816D5}
AppName=AstroPanel
AppVersion={#AppVersion}
AppPublisher=AstroPanel
AppPublisherURL=https://github.com/cjacqueslf/AstroPanel
DefaultDirName={localappdata}\Programs\AstroPanel
DefaultGroupName=AstroPanel
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=AstroPanel-{#AppVersion}-Setup-Windows-x64
SetupIconFile=..\src\astropanel\resources\astropanel-icon.ico
UninstallDisplayIcon={app}\AstroPanel.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "..\dist\AstroPanel\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userdesktop}\AstroPanel"; Filename: "{app}\AstroPanel.exe"; WorkingDir: "{app}"; AppUserModelID: "AstroPanel.Desktop.1"
Name: "{userprograms}\AstroPanel\AstroPanel"; Filename: "{app}\AstroPanel.exe"; WorkingDir: "{app}"; AppUserModelID: "AstroPanel.Desktop.1"
Name: "{userprograms}\AstroPanel\Desinstalar AstroPanel"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\AstroPanel.exe"; Description: "Abrir AstroPanel"; Flags: nowait postinstall skipifsilent
