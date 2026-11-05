; UltraFrontEnd-Setup.exe: installs Ultra Front End for this Windows account (Inno Setup 6.7+).
; Built by tools/release.py:  ISCC /DAppVersion=1.2.1 /DSourceExe=<path to UltraFrontEnd.exe> /DOutDir=<folder> installer\UltraFrontEnd.iss
; /DTest gives a separate name, folder and Apps entry, for trying Setup and Uninstall without touching the real install.
;
; It goes in %LOCALAPPDATA%\Programs\Ultra Front End (the user's own folder, as Discord, Spotify and VS Code install), so
; Windows never asks for administrator permission and the app keeps updating itself. Settings aren't copied: the app finds
; the ones the copy used before where they are (settings-folder.txt, see server.data_folder).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceExe
  #define SourceExe "..\dist\release\UltraFrontEnd.exe"
#endif
#ifndef OutDir
  #define OutDir "..\dist"
#endif
#ifdef Test
  #define AppName "Ultra Front End Test"
  #define AppGuid "{{0B6A4C2E-3D2F-4F8E-9A51-7C0D2B9E6A10}"
#else
  #define AppName "Ultra Front End"
  #define AppGuid "{{F96F918D-9F0D-43DC-8972-28EAB3FEC1EE}"
#endif

[Setup]
AppId={#AppGuid}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=ImSammyTTV
AppPublisherURL=https://github.com/ImSammyTTV/Ultra-Front-End
AppSupportURL=https://github.com/ImSammyTTV/Ultra-Front-End/issues
DefaultDirName={localappdata}\Programs\{#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir={#OutDir}
OutputBaseFilename=UltraFrontEnd-Setup
SetupIconFile=..\app\icon.ico
UninstallDisplayIcon={app}\UltraFrontEnd.exe
UninstallDisplayName={#AppName}
WizardStyle=modern dynamic
WizardImageFile=wizard.bmp,wizard-2x.bmp
WizardSmallImageFile=wizard-small.bmp,wizard-small-2x.bmp
Compression=lzma2/max
SolidCompression=yes
CloseApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Messages]
WelcomeLabel2=This installs [name/ver] for your Windows account.%n%nIt goes in your own user folder, so Windows won't ask for administrator permission, and it keeps itself up to date. If you used Ultra Front End before, your settings and games come with it.
FinishedLabel=[name] is installed. You'll find it in the Start menu and on your desktop.

[Tasks]
Name: "desktopicon"; Description: "Put a shortcut on the desktop"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#SourceExe}"; DestDir: "{app}"; DestName: "UltraFrontEnd.exe"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\UltraFrontEnd.exe"; WorkingDir: "{app}"; Comment: "{#AppName}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\UltraFrontEnd.exe"; WorkingDir: "{app}"; Comment: "{#AppName}"; Tasks: desktopicon

[Run]
Filename: "{app}\UltraFrontEnd.exe"; Description: "Open {#AppName} now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; what the app made beside itself: older builds kept from updates, its browser cache
Type: files; Name: "{app}\UltraFrontEnd.old*.exe"
Type: files; Name: "{app}\UltraFrontEnd.bad-*.exe"
Type: files; Name: "{app}\UltraFrontEnd.exe.download"
Type: filesandordirs; Name: "{app}\webview"

[Code]
const
  UNINSTALL_KEY = 'Software\Microsoft\Windows\CurrentVersion\Uninstall';

{ Stops copies running from the install folder (the window and the helper in the tray), and no others. }
procedure StopRunningCopies();
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -Command "$d = ''' + ExpandConstant('{app}') + '\''; ' +
    'Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($d, [StringComparison]::OrdinalIgnoreCase) } | Stop-Process -Force"',
    '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(500);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningCopies();
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  { the Apps entry the first installer (1.2.0) made: this one replaces it }
  if (CurStep = ssPostInstall) and (ExpandConstant('{#AppName}') = 'Ultra Front End') then
    RegDeleteKeyIncludingSubkeys(HKCU, UNINSTALL_KEY + '\UltraFrontEnd');
end;

function InitializeUninstall(): Boolean;
begin
  StopRunningCopies();
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Note, Data: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#AppName}');
  Data := ExpandConstant('{app}\data');
  if DirExists(Data) and not UninstallSilent() then
    if MsgBox('Also delete your settings, artwork, captures and recordings?' + #13#10#13#10 +
              'Choose No to keep them, so they''re there if you install {#AppName} again.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      DelTree(Data, True, True, True);
      { the note telling a new copy where these settings were }
      Note := ExpandConstant('{localappdata}\Ultra Front End\settings-folder.txt');
      DeleteFile(Note);
    end;
  RemoveDir(ExpandConstant('{app}'));
end;
