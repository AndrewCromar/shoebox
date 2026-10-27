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

[Tasks]
Name: "desktopicon"; Description: "Put a Shoebox shortcut on the desktop"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\Shoebox\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; an update replaces the whole app folder, so files from an older version don't linger
Type: filesandordirs; Name: "{app}\_internal"

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
