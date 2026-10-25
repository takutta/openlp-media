; Installer of the folder plugins for Windows, made by tools/build.py with Inno Setup:
;     ISCC /DAppVersion=1.0.0 /DStageDir=<staged files> /DOutputDir=<dist> tools/installer.iss
; The plugins are copied to the folder where OpenLP looks for community plugins. No administrator rights are needed.

[Setup]
AppId={{6F0B3C3E-2E55-4C8B-9C0F-6D1C5E7A9B21}
AppName=OpenLP:n kansiopluginit
AppVersion={#AppVersion}
AppPublisher=takutta
AppPublisherURL=https://github.com/takutta/openlp-folder-plugins
DefaultDirName={userappdata}\openlp\data\contrib\plugins
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
; The uninstaller is kept out of the plugin folder, which OpenLP searches for plugins
UninstallFilesDir={userappdata}\openlp\data\contrib\folder-plugins-uninstall
UninstallDisplayName=OpenLP:n kansiopluginit
InfoAfterFile={#StageDir}\ASENNUSOHJE.txt
OutputDir={#OutputDir}
OutputBaseFilename=openlp-folder-plugins-{#AppVersion}-setup
WizardStyle=modern
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "fi"; MessagesFile: "compiler:Languages\Finnish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[InstallDelete]
; Remove the files of an earlier version first, so that no stale modules are left behind
Type: filesandordirs; Name: "{app}\filesystem_library"
Type: filesandordirs; Name: "{app}\media_folder"
Type: filesandordirs; Name: "{app}\image_folder"
Type: filesandordirs; Name: "{app}\presentation_folder"
Type: filesandordirs; Name: "{app}\song_folder"

[Files]
Source: "{#StageDir}\plugins\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[UninstallDelete]
; Python writes __pycache__ folders next to the plugins when OpenLP runs
Type: filesandordirs; Name: "{app}\filesystem_library"
Type: filesandordirs; Name: "{app}\media_folder"
Type: filesandordirs; Name: "{app}\image_folder"
Type: filesandordirs; Name: "{app}\presentation_folder"
Type: filesandordirs; Name: "{app}\song_folder"

[Code]
function IsOpenLPRunning(): Boolean;
var
  Locator, Service, Processes: Variant;
begin
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('.', 'root\CIMV2');
    Processes := Service.ExecQuery('SELECT ProcessId FROM Win32_Process WHERE Name = ''OpenLP.exe''');
    Result := Processes.Count > 0;
  except
    Result := False;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  if IsOpenLPRunning() then
    Result := 'Sulje OpenLP ja käynnistä asennus uudelleen. / Close OpenLP and run the installer again.'
  else
    Result := '';
end;
