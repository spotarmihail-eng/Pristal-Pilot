#define MyAppName "Pristal-Pilot"
#define MyAppVersion "0.7.0"
#define MyAppPublisher "MrSkrenh"
#define MyAppExeName "Pristal-Pilot.exe"
[Setup]
AppId={{A6D8C912-77C5-4DB8-8B42-A6D8C9127701}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Pristal-Pilot
DefaultGroupName={#MyAppName}
OutputDir=dist
OutputBaseFilename=Pristal-Pilot-Setup
Compression=lzma
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
[Files]
Source: "dist\Pristal-Pilot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"
[Icons]
Name: "{group}\Pristal-Pilot"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Pristal-Pilot"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить Pristal-Pilot"; Flags: postinstall nowait skipifsilent
