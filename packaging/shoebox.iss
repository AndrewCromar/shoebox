; Windows installer for Shoebox (Inno Setup 6). The GitHub workflow builds it:
;   iscc /DVersion=0.9.0 packaging\shoebox.iss   -> dist\Shoebox-Setup.exe
; Installs for the current user (no admin password), adds Start menu (+ optional desktop) shortcuts, and an
; uninstaller in "Add or remove programs". Running a newer Setup over it updates it in place.
; /UPDATE=1 (used by Shoebox's own updater) opens Shoebox again when the update is done.

#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{6E3B2C1A-5D7F-4F2E-9B8A-3C1D0E5F7A21}
AppName=Shoebox
AppVersion={#Version}
AppVerName=Shoebox {#Version}
AppPublisher=Andrew Cromar
AppPublisherURL=https://github.com/AndrewCromar/shoebox
DefaultDirName={localappdata}\Programs\Shoebox
DefaultGroupName=Shoebox
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Shoebox-Setup
SetupIconFile=build\shoebox.ico
UninstallDisplayIcon={app}\Shoebox.exe
UninstallDisplayName=Shoebox
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ChangesAssociations=yes

[Tasks]
Name: "desktopicon"; Description: "Put a Shoebox shortcut on the desktop"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\Shoebox\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; an update replaces the whole app folder, so files from an older version don't linger
Type: filesandordirs; Name: "{app}\_internal"

[Registry]
; "Open with" -> Shoebox for photos, videos and audio, and Shoebox in Settings > Default apps (it never makes
; itself the default: you choose that). All of it goes when Shoebox is uninstalled.
Root: HKCU; Subkey: "Software\Classes\Shoebox.Media"; ValueType: string; ValueData: "Shoebox"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Shoebox.Media\DefaultIcon"; ValueType: string; ValueData: "{app}\Shoebox.exe,0"
Root: HKCU; Subkey: "Software\Classes\Shoebox.Media\shell\open\command"; ValueType: string; ValueData: """{app}\Shoebox.exe"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "Shoebox"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\shell\open\command"; ValueType: string; ValueData: """{app}\Shoebox.exe"" ""%1"""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "Shoebox"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Shoebox\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Photo, video and audio viewer"
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "Shoebox"; ValueData: "Software\Shoebox\Capabilities"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.3gp\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".3gp"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".3gp"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.aac\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".aac"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".aac"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.aif\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".aif"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".aif"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.aiff\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".aiff"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".aiff"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.avi\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".avi"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".avi"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.bmp\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".bmp"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".bmp"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.flac\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".flac"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".flac"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.gif\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".gif"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".gif"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.heic\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".heic"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".heic"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.heif\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".heif"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".heif"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.jpeg\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".jpeg"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".jpeg"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.jpg\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".jpg"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".jpg"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.m4a\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".m4a"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".m4a"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.m4v\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".m4v"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".m4v"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.mkv\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".mkv"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mkv"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.mov\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".mov"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mov"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.mp3\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".mp3"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mp3"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.mp4\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".mp4"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mp4"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.mts\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".mts"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mts"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.ogg\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".ogg"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ogg"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.opus\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".opus"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".opus"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.png\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".png"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".png"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.tif\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".tif"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".tif"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.tiff\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".tiff"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".tiff"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.wav\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".wav"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".wav"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.webm\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".webm"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".webm"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.webp\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".webp"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".webp"; ValueData: "Shoebox.Media"
Root: HKCU; Subkey: "Software\Classes\.wma\OpenWithProgids"; ValueType: string; ValueName: "Shoebox.Media"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\Shoebox.exe\SupportedTypes"; ValueType: string; ValueName: ".wma"; ValueData: ""
Root: HKCU; Subkey: "Software\Shoebox\Capabilities\FileAssociations"; ValueType: string; ValueName: ".wma"; ValueData: "Shoebox.Media"

[Icons]
Name: "{autoprograms}\Shoebox"; Filename: "{app}\Shoebox.exe"
Name: "{autodesktop}\Shoebox"; Filename: "{app}\Shoebox.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Shoebox.exe"; Description: "Open Shoebox now"; Flags: nowait postinstall skipifsilent
Filename: "{app}\Shoebox.exe"; Flags: nowait; Check: IsUpdate

[UninstallDelete]
; thumbnails are only a cache; your photos are never inside Shoebox's folders
Type: filesandordirs; Name: "{localappdata}\Shoebox"

[Code]
function IsUpdate: Boolean;
begin
  Result := ExpandConstant('{param:UPDATE|0}') = '1';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { settings: the chosen photos folder etc. Kept unless you say so (a silent uninstall keeps them). }
  if (CurUninstallStep = usPostUninstall) and DirExists(ExpandConstant('{userappdata}\Shoebox')) then
    if SuppressibleMsgBox('Also remove Shoebox''s settings (which photos folder you picked)?' + #13#10 +
                          'Your photos are not touched either way.', mbConfirmation, MB_YESNO, IDNO) = IDYES then
      DelTree(ExpandConstant('{userappdata}\Shoebox'), True, True, True);
end;
