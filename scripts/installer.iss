; Inno Setup script — wrap VoiceInputStudio.exe into a Windows installer.
; Build with: ISCC.exe scripts\installer.iss
; Output: dist\VoiceInputStudio-Setup.exe

#define MyAppName "Voice Input Studio"
#define MyAppVersion "1.5.0"
#define MyAppPublisher "Voice Input Studio"
#define MyAppExeName "VoiceInputStudio.exe"

[Setup]
AppId={{B5F3F6F4-3D1F-4C9A-9E33-E4F4C1F5E8A1}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\VoiceInputStudio
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\dist
OutputBaseFilename=VoiceInputStudio-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
WizardStyle=modern

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startupicon"; Description: "Windows起動時に自動で起動する"; GroupDescription: "追加タスク"; Flags: unchecked
Name: "desktopicon"; Description: "デスクトップにショートカットを作成"; GroupDescription: "追加タスク"; Flags: unchecked

[Files]
Source: "..\dist\VoiceInputStudio.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\アンインストール"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "今すぐ起動"; Flags: nowait postinstall skipifsilent
