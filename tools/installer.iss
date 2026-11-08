; Installer of the folder plugins for Windows, made by tools/build.py with Inno Setup:
;     ISCC /DAppVersion=0.0.2 /DStageDir=<staged files> /DOutputDir=<dist> tools/installer.iss
; The plugins are copied into the plugins folder of the OpenLP the user chooses, next to OpenLP's own plugins, so a
; portable OpenLP keeps them when it is moved. Administrator rights are only needed for an OpenLP in Program Files.

[Setup]
AppId={{6F0B3C3E-2E55-4C8B-9C0F-6D1C5E7A9B21}
AppName={cm:AppName}
AppVersion={#AppVersion}
AppPublisher=takutta
AppPublisherURL=https://github.com/takutta/openlp-media
DefaultDirName={commonpf64}\OpenLP
DisableDirPage=no
DirExistsWarning=no
AppendDefaultDirName=no
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
; The uninstaller is kept out of the plugins folder, which OpenLP searches for plugins
UninstallFilesDir={app}\folder-plugins-uninstall
UninstallDisplayName={cm:AppName}
OutputDir={#OutputDir}
OutputBaseFilename=openlp-folder-plugins-{#AppVersion}-setup
WizardStyle=modern
; The language is asked first, the language of Windows is preselected
ShowLanguageDialog=yes
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"; InfoAfterFile: "{#StageDir}\INSTALL.txt"
Name: "fi"; MessagesFile: "compiler:Languages\Finnish.isl"; InfoAfterFile: "{#StageDir}\ASENNUSOHJE.txt"

[CustomMessages]
en.AppName=OpenLP Folder Plugins
fi.AppName=OpenLP:n kansiopluginit
en.OpenLPRunning=Close OpenLP and run the installer again.
fi.OpenLPRunning=Sulje OpenLP ja käynnistä asennus uudelleen.
en.SelectOpenLP=Choose the folder of OpenLP: the folder of a portable OpenLP (the one with OpenLPPortable.exe) or the folder where OpenLP is installed (the one with OpenLP.exe).
fi.SelectOpenLP=Valitse OpenLP:n kansio: siirrettävän OpenLP:n kansio (jossa on OpenLPPortable.exe) tai kansio, johon OpenLP on asennettu (jossa on OpenLP.exe).
en.NotOpenLP=OpenLP was not found in this folder. Choose the folder with OpenLPPortable.exe or OpenLP.exe.
fi.NotOpenLP=Kansiosta ei löytynyt OpenLP:tä. Valitse kansio, jossa on OpenLPPortable.exe tai OpenLP.exe.
en.NoWriteAccess=You have no permission to write to this folder. Run the installer again and choose to install for all users, or choose another folder.
fi.NoWriteAccess=Sinulla ei ole oikeutta kirjoittaa tähän kansioon. Käynnistä asennus uudelleen ja valitse asennus kaikille käyttäjille, tai valitse toinen kansio.

[InstallDelete]
; Remove the files of an earlier version first, so that no stale modules are left behind
Type: filesandordirs; Name: "{code:CodeDir}\filesystem_library"
Type: filesandordirs; Name: "{code:CodeDir}\media_folder"
Type: filesandordirs; Name: "{code:CodeDir}\image_folder"
Type: filesandordirs; Name: "{code:CodeDir}\presentation_folder"
Type: filesandordirs; Name: "{code:CodeDir}\song_folder"
Type: filesandordirs; Name: "{code:PluginDir}\media_folder"
Type: filesandordirs; Name: "{code:PluginDir}\image_folder"
Type: filesandordirs; Name: "{code:PluginDir}\presentation_folder"
Type: filesandordirs; Name: "{code:PluginDir}\song_folder"
; Versions before 0.0.1 were installed into the community plugin folder. OpenLP would load them a second time.
Type: filesandordirs; Name: "{userappdata}\openlp\data\contrib\plugins\filesystem_library"
Type: filesandordirs; Name: "{userappdata}\openlp\data\contrib\plugins\media_folder"
Type: filesandordirs; Name: "{userappdata}\openlp\data\contrib\plugins\image_folder"
Type: filesandordirs; Name: "{userappdata}\openlp\data\contrib\plugins\presentation_folder"
Type: filesandordirs; Name: "{userappdata}\openlp\data\contrib\plugins\song_folder"
Type: filesandordirs; Name: "{userappdata}\openlp\data\contrib\folder-plugins-uninstall"

[Files]
; The official build has OpenLP's own modules inside OpenLP.exe and looks for plugins by their *plugin.py files in
; the plugins folder next to it. The code goes where Python finds openlp.plugins.* modules on disk, and a copy of each
; *plugin.py file goes into the plugins folder, so that OpenLP finds the plugin. The copy itself is never run.
Source: "{#StageDir}\plugins\*"; DestDir: "{code:CodeDir}"; Flags: recursesubdirs ignoreversion
Source: "{#StageDir}\plugins\media_folder\media_folder_plugin.py"; DestDir: "{code:PluginDir}\media_folder"; Flags: ignoreversion
Source: "{#StageDir}\plugins\image_folder\image_folder_plugin.py"; DestDir: "{code:PluginDir}\image_folder"; Flags: ignoreversion
Source: "{#StageDir}\plugins\presentation_folder\presentation_folder_plugin.py"; DestDir: "{code:PluginDir}\presentation_folder"; Flags: ignoreversion
Source: "{#StageDir}\plugins\song_folder\song_folder_plugin.py"; DestDir: "{code:PluginDir}\song_folder"; Flags: ignoreversion

[UninstallDelete]
; Python writes __pycache__ folders next to the plugins when OpenLP runs
Type: filesandordirs; Name: "{code:CodeDir}\filesystem_library"
Type: filesandordirs; Name: "{code:CodeDir}\media_folder"
Type: filesandordirs; Name: "{code:CodeDir}\image_folder"
Type: filesandordirs; Name: "{code:CodeDir}\presentation_folder"
Type: filesandordirs; Name: "{code:CodeDir}\song_folder"
Type: filesandordirs; Name: "{code:PluginDir}\media_folder"
Type: filesandordirs; Name: "{code:PluginDir}\image_folder"
Type: filesandordirs; Name: "{code:PluginDir}\presentation_folder"
Type: filesandordirs; Name: "{code:PluginDir}\song_folder"

[Code]
// The folder of OpenLP.exe: App\OpenLP in a portable OpenLP, the chosen folder itself in an installed one.
// Only the official build (with its _internal folder) is accepted, because the files are put inside it.
function OpenLPAppDir(Folder: String): String;
begin
  Folder := RemoveBackslashUnlessRoot(Folder);
  if FileExists(Folder + '\App\OpenLP\OpenLP.exe') then
    Folder := Folder + '\App\OpenLP';
  if FileExists(Folder + '\OpenLP.exe') and DirExists(Folder + '\_internal') then
    Result := Folder
  else
    Result := '';
end;

// OpenLP looks for plugins in the plugins folder next to OpenLP.exe
function PluginDir(Param: String): String;
begin
  Result := OpenLPAppDir(ExpandConstant('{app}')) + '\plugins';
end;

// Python finds the openlp.plugins.* modules of the official build on disk in this folder
function CodeDir(Param: String): String;
begin
  Result := OpenLPAppDir(ExpandConstant('{app}')) + '\_internal\openlp\plugins';
end;

procedure InitializeWizard();
begin
  WizardForm.SelectDirLabel.Caption := CustomMessage('SelectOpenLP');
  // Earlier versions remembered the community plugin folder, which is not an OpenLP folder
  if OpenLPAppDir(WizardForm.DirEdit.Text) = '' then
    WizardForm.DirEdit.Text := ExpandConstant('{commonpf64}\OpenLP');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  AppDir, TestFile: String;
begin
  Result := True;
  if CurPageID <> wpSelectDir then
    exit;
  AppDir := OpenLPAppDir(WizardDirValue());
  if AppDir = '' then begin
    MsgBox(CustomMessage('NotOpenLP'), mbError, MB_OK);
    Result := False;
    exit;
  end;
  TestFile := AppDir + '\plugins\.folder-plugins-write-test';
  if SaveStringToFile(TestFile, '', False) then
    DeleteFile(TestFile)
  else begin
    MsgBox(CustomMessage('NoWriteAccess'), mbError, MB_OK);
    Result := False;
  end;
end;

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
    Result := CustomMessage('OpenLPRunning')
  else
    Result := '';
end;
