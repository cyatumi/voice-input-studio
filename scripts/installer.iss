; Inno Setup script 窶・wrap VoiceInputStudio.exe into a Windows installer.
; Build with: ISCC.exe scripts\installer.iss
; Output: dist\VoiceInputStudio-Setup.exe

#define MyAppName "Voice Input Studio"
#define MyAppVersion "1.5.2"
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
Name: "startupicon"; Description: "Windows襍ｷ蜍墓凾縺ｫ閾ｪ蜍輔〒襍ｷ蜍輔☆繧・; GroupDescription: "霑ｽ蜉繧ｿ繧ｹ繧ｯ"; Flags: unchecked
Name: "desktopicon"; Description: "繝・せ繧ｯ繝医ャ繝励↓繧ｷ繝ｧ繝ｼ繝医き繝・ヨ繧剃ｽ懈・"; GroupDescription: "霑ｽ蜉繧ｿ繧ｹ繧ｯ"; Flags: unchecked

[Files]
Source: "..\dist\VoiceInputStudio.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\繧｢繝ｳ繧､繝ｳ繧ｹ繝医・繝ｫ"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "莉翫☆縺占ｵｷ蜍・; Flags: nowait postinstall skipifsilent

